"""
Chat Service — Per-session WebSocket handler with LangGraph Claims Pipeline.

Architecture:
  PRIMARY PATH:  12-node Claims StateGraph (Gemini/Ollama LLM + DB tools + RAG)
  FALLBACK PATH: RAG-only similarity lookup (no LLM reasoning)

Resilience features:
- Graph initialization failure → graceful fallback to RAG-only
- LLM timeout → auto-escalate to human agent
- Circuit breaker → prevents cascading LLM/embedding failures
- Per-session locks → prevent race conditions on concurrent mutations

NOTE: Graph execution logic is in graph_executor.py.
      DB persistence logic is in message_persister.py.
"""

import json
import random
import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from backend.config import get_settings
from backend.services.resilience import (
    llm_circuit, embedding_circuit,
    with_timeout, TimeoutError,
    get_fallback_response,
    handle_agent_disconnect, handle_user_disconnect,
)
from backend.services.tracing import (
    RequestTrace, trace_store, broadcast_trace,
)
from backend.services.graph_executor import (
    execute_claims_graph, init_claims_graph_async,
)
from backend.services.message_persister import (
    persist_message as _persist_message,
    persist_escalation as _persist_escalation,
    build_agent_messages as _build_agent_messages,
)

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# --- Per-session asyncio locks to prevent concurrent mutation ---
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

def get_session_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session lock for safe concurrent access."""
    return _session_locks[session_id]


def _cleanup_session_lock(session_id: str):
    """Remove the per-session lock when the session's last WS disconnects."""
    if session_id in _session_locks:
        del _session_locks[session_id]
        logger.debug(f"🧹 Cleaned up session lock for {session_id}")


# ==============================================================
# RAG-ONLY AI RESPONSE (Fallback Path — no LLM reasoning)
# ==============================================================


async def get_rag_ai_response(query: str) -> dict:
    """
    Generate an AI response using RAG similarity lookup only.
    No LLM reasoning — just returns the closest knowledge base match.
    Used as fallback when the LangGraph agent is unavailable.
    """
    if not llm_circuit.can_execute():
        logger.warning("🔌 LLM circuit OPEN — using fallback")
        return get_fallback_response("circuit_open")

    if not embedding_circuit.can_execute():
        logger.warning("🔌 Embedding circuit OPEN — using fallback")
        return get_fallback_response("embedding_failure")

    try:
        from backend.services.rag_service import async_retrieve_context

        results = await with_timeout(
            async_retrieve_context(query),
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            operation_name="RAG_retrieval"
        )

        embedding_circuit.record_success()

        if results and results[0]["similarity"] >= settings.RAG_SIMILARITY_THRESHOLD:
            top = results[0]
            confidence = int(top["similarity"] * 100)
            response_text = top["metadata"].get("reponse", top["chunk_text"])
            source_type = top["source_type"]
            is_hitl = source_type == "hitl_validated"

            llm_circuit.record_success()
            return {
                "text": response_text,
                "confidence": confidence,
                "source": source_type,
                "hitl_boosted": is_hitl,
                "similarity": top["similarity"],
                "degraded": False,
            }
        elif results:
            top = results[0]
            confidence = int(top["similarity"] * 100)

            if confidence < int(settings.CONFIDENCE_THRESHOLD * 100):
                return {"text": None, "confidence": confidence, "degraded": False}
            else:
                response_text = top["metadata"].get("reponse", top["chunk_text"])
                llm_circuit.record_success()
                return {
                    "text": response_text,
                    "confidence": confidence,
                    "source": top["source_type"],
                    "degraded": False,
                }
        else:
            return {"text": None, "confidence": 0, "degraded": False}

    except TimeoutError:
        llm_circuit.record_failure()
        logger.error(f"⏰ RAG retrieval timed out for query: {query[:50]}")
        return get_fallback_response("timeout")

    except Exception as e:
        embedding_circuit.record_failure()
        logger.error(f"❌ RAG retrieval failed: {e}")
        return get_fallback_response("default")


# ==============================================================
# SIMULATED AI RESPONSE (last resort — no RAG store)
# ==============================================================

def get_simulated_ai_response(query: str) -> dict:
    """Hardcoded responses for demo — used when RAG store is empty."""
    q = query.lower()
    responses = {
        "dentaire": ("Selon l'Article 4, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire.", 94),
        "remboursement": ("Les remboursements sont traites sous 48h ouvrees pour les FSE. Les feuilles papier: 15 jours ouvres.", 88),
        "naissance": ("La prime de naissance est de 300 TND par enfant, versee sur presentation de l'acte de naissance.", 91),
        "urgence": ("En cas d'urgence, les frais sont pris en charge a 100%. Numero d'urgence I-Way: 71 800 800.", 96),
        "humain": (None, 15),
        "agent": (None, 20),
        "parler": (None, 18),
    }
    for keyword, (text, confidence) in responses.items():
        if keyword in q:
            return {"text": text, "confidence": confidence}
    return {
        "text": "D'apres la base de connaissances I-Way, je vous recommande de consulter votre espace adherent ou de contacter notre service client au 71 800 800.",
        "confidence": 72
    }


# ==============================================================
# MAIN WEBSOCKET HANDLER
# ==============================================================

async def handle_chat_websocket(websocket: WebSocket, session_id: str, sessions_store: dict, ws_manager):
    """
    Per-session WebSocket handler with full resilience.
    
    AI Response Strategy (ordered by priority):
    1. LangGraph Agent (tools + LLM reasoning) — primary
    2. RAG-only similarity lookup — fallback if agent fails
    3. Simulated hardcoded responses — last resort if RAG store is empty
    
    Concurrency: Uses per-session asyncio.Lock to prevent race conditions
    when user and agent WebSockets mutate session state simultaneously.
    """
    session = sessions_store.get(session_id)
    if not session:
        await websocket.close(code=4004)
        return

    lock = get_session_lock(session_id)
    await websocket.accept()
    is_agent = False

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "agent_connect":
                is_agent = True
                async with lock:
                    session["agent_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "agent", "session_id": session_id})
                continue

            if msg_type == "user_connect":
                async with lock:
                    session["user_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "user", "session_id": session_id})
                await websocket.send_json({"type": "history", "messages": session["history"]})
                continue

            if msg_type == "user_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                user_msg = {"role": "user", "content": content, "timestamp": datetime.now().isoformat()}
                async with lock:
                    session["history"].append(user_msg)
                asyncio.create_task(_persist_message(session_id, "user", content))

                if session["status"] == "agent_connected":
                    # Relay to human agent
                    agent_ws = session.get("agent_ws")
                    if agent_ws:
                        try:
                            await agent_ws.send_json({"type": "user_message", "content": content, "timestamp": user_msg["timestamp"]})
                        except Exception:
                            handle_agent_disconnect(session, sessions_store)
                            await websocket.send_json({"type": "handoff_started", "reason": "Agent disconnected — re-queued"})

                elif session["status"] == "handoff_pending":
                    # Graph handles this via pre_intake_router → stall_node
                    await websocket.send_json({"type": "thinking", "status": "Réflexion en cours...", "node": "stall"})

                    trace = RequestTrace(
                        session_id=session_id,
                        user_matricule=session.get("user_matricule", ""),
                        query=content,
                    )
                    span_recv = trace.start_span("RECEIVED", message_length=len(content))
                    span_recv.finish()

                    ai_result = None

                    if llm_circuit.can_execute():
                        span_graph = trace.start_span("GRAPH_STALL_EXECUTION")
                        try:
                            ai_result = await asyncio.wait_for(
                                execute_claims_graph(content, session, websocket),
                                timeout=settings.LLM_TIMEOUT_SECONDS + 10
                            )
                            if ai_result:
                                span_graph.finish(source="claims_graph_stall")
                                llm_circuit.record_success()
                            else:
                                span_graph.finish(status="graph_unavailable")
                        except asyncio.TimeoutError:
                            span_graph.finish(status="timeout")
                            llm_circuit.record_failure()
                        except Exception as e:
                            span_graph.finish(status="error", error=str(e))

                    if ai_result is None:
                        ai_result = {
                            "text": "Je comprends votre impatience. Un agent va vous répondre très bientôt.",
                            "confidence": 0,
                            "source": "fallback",
                        }

                    if ai_result and ai_result.get("text"):
                        response_text = ai_result["text"]
                        confidence = ai_result.get("confidence", 50)

                        # Stream tokens if not already streamed by graph
                        if ai_result.get("source") != "claims_graph":
                            words = response_text.split(" ")
                            for i, word in enumerate(words):
                                token = word + (" " if i < len(words) - 1 else "")
                                await websocket.send_json({"type": "ai_token", "token": token})
                                await asyncio.sleep(0.03 + random.random() * 0.05)

                        await websocket.send_json({
                            "type": "ai_done",
                            "text": response_text,
                            "confidence": confidence,
                            "is_handoff_ai": True,
                            "source": ai_result.get("source", "handoff_ai"),
                        })
                        session["history"].append({
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": datetime.now().isoformat(),
                            "confidence": confidence,
                            "is_handoff_ai": True,
                        })
                        asyncio.create_task(_persist_message(
                            session_id, "assistant", response_text,
                            confidence=confidence, model_used=ai_result.get("source", "handoff_ai")
                        ))
                        session["last_ai_confidence"] = confidence
                        trace.finish("STALL_RESOLVED", confidence=confidence)
                    else:
                        await websocket.send_json({
                            "type": "ai_done",
                            "confidence": 0,
                            "is_handoff_ai": True,
                            "text": "Je comprends votre frustration. Un agent va vous répondre très bientôt.",
                        })
                        trace.finish("STALL_FALLBACK", confidence=0)

                    trace_store.add(trace)
                    await broadcast_trace(trace)

                else:
                    # === PRIMARY AI FLOW (session.status == "active") ===
                    await websocket.send_json({"type": "thinking", "status": "Analyse de votre demande...", "node": "intake"})

                    # --- Start trace ---
                    trace = RequestTrace(
                        session_id=session_id,
                        user_matricule=session.get("user_matricule", ""),
                        query=content,
                    )
                    span_recv = trace.start_span("RECEIVED", message_length=len(content))
                    span_recv.finish()

                    ai_result = None

                    # -- TIER 1: Claims StateGraph (primary) --
                    if llm_circuit.can_execute():
                        span_graph = trace.start_span("GRAPH_EXECUTION")
                        try:
                            ai_result = await asyncio.wait_for(
                                execute_claims_graph(content, session, websocket),
                                timeout=settings.LLM_TIMEOUT_SECONDS + 15
                            )
                            if ai_result:
                                span_graph.finish(
                                    tools=ai_result.get("tools_called", []),
                                    source="claims_graph",
                                    intent=ai_result.get("intent"),
                                )
                                llm_circuit.record_success()
                            else:
                                span_graph.finish(status="graph_unavailable")
                        except asyncio.TimeoutError:
                            span_graph.finish(status="timeout")
                            llm_circuit.record_failure()
                            logger.warning("Graph timed out — falling back to RAG")
                        except Exception as e:
                            span_graph.finish(status="error", error=str(e))
                            logger.warning(f"Graph error: {e} — falling back to RAG")

                    # -- TIER 2: RAG-only fallback --
                    if ai_result is None:
                        from backend.services.rag_service import knowledge_store
                        if knowledge_store.count > 0:
                            span_rag = trace.start_span("RAG_FALLBACK", store_count=knowledge_store.count)
                            ai_result = await get_rag_ai_response(content)
                            span_rag.finish(
                                similarity=ai_result.get("similarity"),
                                source=ai_result.get("source"),
                                degraded=ai_result.get("degraded", False),
                            )
                        else:
                            # -- TIER 3: Simulated response (no RAG store) --
                            span_sim = trace.start_span("SIMULATED_RESPONSE")
                            await asyncio.sleep(0.5 + random.random() * 0.5)
                            ai_result = get_simulated_ai_response(content)
                            span_sim.finish()

                    # --- Evaluate & respond ---
                    span_eval = trace.start_span("EVAL", confidence=ai_result.get("confidence"))

                    # Handle graph responses (tokens already streamed)
                    if ai_result.get("source") == "claims_graph":
                        claim_status = ai_result.get("claim_status", "active")
                        tools_called = ai_result.get("tools_called", [])
                        confidence = ai_result.get("confidence", 0)

                        # ═══ ESCALATION / HANDOFF INTERCEPT ═══
                        if claim_status == "pending_human":
                            span_eval.finish(status="escalation_via_graph")

                            async with lock:
                                session["history"].append({
                                    "role": "assistant",
                                    "content": ai_result["text"],
                                    "timestamp": datetime.now().isoformat(),
                                    "confidence": confidence,
                                    "source": "claims_graph",
                                })
                                asyncio.create_task(_persist_message(
                                    session_id, "assistant", ai_result["text"],
                                    confidence=confidence, model_used="claims_graph"
                                ))

                                # Transition session state
                                session["status"] = "handoff_pending"
                                session["reason"] = f"Graph escalation (confidence: {confidence}%): {content[:80]}"
                                session["trigger_message"] = {
                                    "content": ai_result["text"],
                                    "confidence": confidence,
                                    "query": content,
                                    "intent": ai_result.get("intent"),
                                }
                                session["last_ai_confidence"] = confidence

                                sys_msg = "Un agent humain va vous rejoindre bientôt. Vous pouvez continuer à poser des questions en attendant."
                                session["history"].append({
                                    "role": "system",
                                    "content": sys_msg,
                                    "timestamp": datetime.now().isoformat(),
                                })
                                asyncio.create_task(_persist_message(session_id, "system", sys_msg))

                            # Tell the user
                            await websocket.send_json({
                                "type": "ai_done",
                                "text": ai_result["text"],
                                "confidence": confidence,
                                "source": "claims_graph",
                                "tools_called": tools_called,
                                "intent": ai_result.get("intent"),
                            })
                            await websocket.send_json({
                                "type": "handoff_started",
                                "reason": session["reason"],
                                "keep_chatting": True,
                            })

                            # Notify agent dashboard in real time
                            await ws_manager.broadcast({
                                "type": "NEW_ESCALATION",
                                "payload": {
                                    "session_id": session_id,
                                    "user_name": session["user_name"],
                                    "user_role": session["user_role"],
                                    "reason": session["reason"],
                                    "created_at": session["created_at"],
                                    "intent": ai_result.get("intent"),
                                }
                            })

                            asyncio.create_task(_persist_escalation(
                                session_id, session["reason"]
                            ))

                            trace.finish(
                                "HUMAN_ESCALATED",
                                confidence=confidence,
                                source_type="claims_graph",
                            )
                        else:
                            # ═══ NORMAL GRAPH RESOLVED ═══
                            span_eval.finish(status="graph_resolved")
                            await websocket.send_json({
                                "type": "ai_done",
                                "text": ai_result["text"],
                                "confidence": confidence,
                                "source": "claims_graph",
                                "tools_called": tools_called,
                                "intent": ai_result.get("intent"),
                            })
                            session["history"].append({
                                "role": "assistant",
                                "content": ai_result["text"],
                                "timestamp": datetime.now().isoformat(),
                                "confidence": confidence,
                                "source": "claims_graph",
                            })
                            asyncio.create_task(_persist_message(
                                session_id, "assistant", ai_result["text"],
                                confidence=confidence, model_used="claims_graph"
                            ))
                            session["last_ai_confidence"] = confidence
                            trace.finish(
                                "GRAPH_RESOLVED",
                                confidence=confidence,
                                source_type="claims_graph",
                            )

                    # Handle degraded responses (timeout/circuit open)
                    elif ai_result.get("degraded"):
                        span_eval.finish(status="degraded", failure_type=ai_result.get("failure_type"))
                        trace.finish("DEGRADED", confidence=0)

                        async with lock:
                            session["trigger_message"] = {
                                "content": ai_result["text"],
                                "confidence": 0,
                                "reason": f"Service degradation ({ai_result.get('failure_type', 'unknown')})",
                            }
                            session["status"] = "handoff_pending"
                            session["reason"] = f"Service degradation ({ai_result.get('failure_type', 'unknown')})"
                            session["history"].append({
                                "role": "system",
                                "content": ai_result["text"],
                                "timestamp": datetime.now().isoformat()
                            })
                            asyncio.create_task(_persist_message(session_id, "system", ai_result["text"]))
                        await websocket.send_json({
                            "type": "handoff_started",
                            "reason": session["reason"],
                            "degraded": True,
                            "keep_chatting": True,
                        })
                        await ws_manager.broadcast({
                            "type": "NEW_ESCALATION",
                            "payload": {
                                "session_id": session_id,
                                "user_name": session["user_name"],
                                "user_role": session["user_role"],
                                "reason": session["reason"],
                                "created_at": session["created_at"],
                                "priority": "high",
                            }
                        })

                    # Handle low confidence → escalate (but AI keeps chatting)
                    elif ai_result["confidence"] < 30 or ai_result["text"] is None:
                        span_eval.finish(status="low_confidence")
                        trace.finish("HUMAN_ESCALATED", confidence=ai_result["confidence"])

                        trigger_text = ai_result.get("text") or "Réponse insuffisante — confidence trop basse"
                        async with lock:
                            session["trigger_message"] = {
                                "content": trigger_text,
                                "confidence": ai_result["confidence"],
                                "query": content,
                            }
                            session["last_ai_confidence"] = ai_result["confidence"]
                            session["status"] = "handoff_pending"
                            session["reason"] = f"Low confidence ({ai_result['confidence']}%) on: {content[:50]}"
                            sys_msg = "Un agent va vous rejoindre bientôt. Vous pouvez continuer à poser des questions en attendant."
                            session["history"].append({
                                "role": "system",
                                "content": sys_msg,
                                "timestamp": datetime.now().isoformat()
                            })
                            asyncio.create_task(_persist_message(session_id, "system", sys_msg))
                        await websocket.send_json({
                            "type": "handoff_started",
                            "reason": session["reason"],
                            "keep_chatting": True,
                        })
                        await ws_manager.broadcast({
                            "type": "NEW_ESCALATION",
                            "payload": {
                                "session_id": session_id,
                                "user_name": session["user_name"],
                                "user_role": session["user_role"],
                                "reason": session["reason"],
                                "created_at": session["created_at"],
                            }
                        })

                    # Handle RAG/simulated responses (need to stream tokens)
                    else:
                        span_eval.finish(status="high_confidence")

                        span_stream = trace.start_span("RESPONSE", confidence=ai_result["confidence"])
                        response_text = ai_result["text"]
                        words = response_text.split(" ")
                        for i, word in enumerate(words):
                            token = word + (" " if i < len(words) - 1 else "")
                            await websocket.send_json({"type": "ai_token", "token": token})
                            await asyncio.sleep(0.03 + random.random() * 0.05)

                        done_payload = {"type": "ai_done", "text": ai_result["text"], "confidence": ai_result["confidence"]}
                        if ai_result.get("source"):
                            done_payload["source"] = ai_result["source"]
                        if ai_result.get("hitl_boosted"):
                            done_payload["hitl_boosted"] = True

                        await websocket.send_json(done_payload)
                        async with lock:
                            session["history"].append({
                                "role": "assistant",
                                "content": response_text,
                                "timestamp": datetime.now().isoformat(),
                                "confidence": ai_result["confidence"],
                                "source": ai_result.get("source", "simulated"),
                            })
                            asyncio.create_task(_persist_message(
                                session_id, "assistant", response_text,
                                confidence=ai_result["confidence"], model_used=ai_result.get("source", "simulated")
                            ))
                            session["last_ai_confidence"] = ai_result["confidence"]
                        span_stream.finish(tokens=len(words))
                        trace.finish(
                            "RAG_RESOLVED" if ai_result.get("source") else "AI_FALLBACK",
                            confidence=ai_result["confidence"],
                            source_type=ai_result.get("source"),
                        )

                    # --- Store & broadcast trace ---
                    trace_store.add(trace)
                    await broadcast_trace(trace)

            elif msg_type == "agent_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                agent_msg = {"role": "agent", "content": content, "timestamp": datetime.now().isoformat()}
                session["history"].append(agent_msg)
                asyncio.create_task(_persist_message(session_id, "agent", content))
                user_ws = session.get("user_ws")
                if user_ws:
                    try:
                        await user_ws.send_json({"type": "agent_message", "content": content, "timestamp": agent_msg["timestamp"]})
                    except Exception:
                        handle_user_disconnect(session)

            elif msg_type == "manual_handoff_request":
                session["status"] = "handoff_pending"
                session["reason"] = "User manually requested a human agent"
                sys_msg_manual = "Vous avez demande a parler a un agent humain. Transfert en cours..."
                session["history"].append({
                    "role": "system",
                    "content": sys_msg_manual,
                    "timestamp": datetime.now().isoformat()
                })
                asyncio.create_task(_persist_message(session_id, "system", sys_msg_manual))
                await websocket.send_json({"type": "handoff_started", "reason": session["reason"], "keep_chatting": True})
                await ws_manager.broadcast({
                    "type": "NEW_ESCALATION",
                    "payload": {
                        "session_id": session_id,
                        "user_name": session["user_name"],
                        "user_role": session["user_role"],
                        "reason": session["reason"],
                        "created_at": session["created_at"],
                    }
                })

            elif msg_type == "PING":
                await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        if is_agent:
            result = handle_agent_disconnect(session, sessions_store)
            if result == "re_queued":
                user_ws = session.get("user_ws")
                if user_ws:
                    try:
                        await user_ws.send_json({
                            "type": "agent_disconnected",
                            "message": "L'agent a ete deconnecte. Recherche d'un nouvel agent..."
                        })
                    except Exception:
                        pass
                await ws_manager.broadcast({
                    "type": "NEW_ESCALATION",
                    "payload": {
                        "session_id": session_id,
                        "user_name": session["user_name"],
                        "user_role": session["user_role"],
                        "reason": session["reason"],
                        "created_at": session["created_at"],
                        "priority": "high",
                    }
                })
        else:
            handle_user_disconnect(session)
        # Clean up per-session lock to prevent memory leak
        _cleanup_session_lock(session_id)
        logger.info(f"Chat WS disconnected from session {session_id} (agent={is_agent})")

    except Exception as e:
        logger.error(f"Chat WS error in session {session_id}: {e}")
        if is_agent:
            handle_agent_disconnect(session, sessions_store)
        else:
            handle_user_disconnect(session)
        # Clean up per-session lock to prevent memory leak
        _cleanup_session_lock(session_id)
