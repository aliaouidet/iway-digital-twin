"""
Chat Service — Per-session WebSocket handler with resilience patterns.

Resilience features:
- LLM timeout → auto-escalate to human agent
- Circuit breaker → prevents cascading LLM/embedding failures
- Agent disconnect → re-queues session for another agent
- User disconnect → preserves state for reconnection
- Graceful degradation → fallback responses when services are down
"""

import json
import random
import asyncio
import logging
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

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


# ==============================================================
# RAG-ENHANCED AI RESPONSE (replaces hardcoded responses)
# ==============================================================

async def get_rag_ai_response(query: str) -> dict:
    """
    Generate an AI response using the RAG pipeline with resilience.
    
    Flow:
    1. Check embedding circuit breaker
    2. Retrieve context from knowledge store (with timeout)
    3. If high-confidence match → return it
    4. If low confidence → trigger handoff
    5. On any failure → graceful degradation
    """
    # --- Check circuit breakers ---
    if not llm_circuit.can_execute():
        logger.warning("🔌 LLM circuit OPEN — using fallback")
        return get_fallback_response("circuit_open")

    if not embedding_circuit.can_execute():
        logger.warning("🔌 Embedding circuit OPEN — using fallback")
        return get_fallback_response("embedding_failure")

    try:
        # --- RAG Retrieval with timeout ---
        from backend.services.rag_service import retrieve_context

        async def _do_retrieval():
            # Run CPU-bound embedding in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, retrieve_context, query)

        results = await with_timeout(
            _do_retrieval(),
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            operation_name="RAG_retrieval"
        )

        embedding_circuit.record_success()

        if results and results[0]["similarity"] >= settings.RAG_SIMILARITY_THRESHOLD:
            # High-confidence RAG match
            top = results[0]
            confidence = int(top["similarity"] * 100)
            response_text = top["metadata"].get("reponse", top["chunk_text"])

            # Mark source for dashboard tracking
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
            # Low confidence — check if we should still return or escalate
            top = results[0]
            confidence = int(top["similarity"] * 100)

            if confidence < int(settings.CONFIDENCE_THRESHOLD * 100):
                # Below threshold → trigger handoff
                return {
                    "text": None,
                    "confidence": confidence,
                    "degraded": False,
                }
            else:
                # Medium confidence — return with caveat
                response_text = top["metadata"].get("reponse", top["chunk_text"])
                llm_circuit.record_success()
                return {
                    "text": response_text,
                    "confidence": confidence,
                    "source": top["source_type"],
                    "degraded": False,
                }
        else:
            # No results at all
            return {
                "text": None,
                "confidence": 0,
                "degraded": False,
            }

    except TimeoutError:
        llm_circuit.record_failure()
        logger.error(f"⏰ RAG retrieval timed out for query: {query[:50]}")
        return get_fallback_response("timeout")

    except Exception as e:
        embedding_circuit.record_failure()
        logger.error(f"❌ RAG retrieval failed: {e}")
        return get_fallback_response("default")


# ==============================================================
# SIMULATED AI RESPONSE (kept as fallback when RAG store is empty)
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
    
    Resilience behaviors:
    - LLM/embedding timeout → auto-escalate with friendly message
    - Circuit breaker open → instant fallback, no waiting
    - Agent disconnect → re-queue session
    - User disconnect → preserve state for reconnection
    """
    session = sessions_store.get(session_id)
    if not session:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    is_agent = False

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "agent_connect":
                is_agent = True
                session["agent_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "agent", "session_id": session_id})
                continue

            if msg_type == "user_connect":
                session["user_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "user", "session_id": session_id})
                await websocket.send_json({"type": "history", "messages": session["history"]})
                continue

            if msg_type == "user_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                user_msg = {"role": "user", "content": content, "timestamp": datetime.now().isoformat()}
                session["history"].append(user_msg)

                if session["status"] == "agent_connected":
                    # Relay to agent
                    agent_ws = session.get("agent_ws")
                    if agent_ws:
                        try:
                            await agent_ws.send_json({"type": "user_message", "content": content, "timestamp": user_msg["timestamp"]})
                        except Exception:
                            # Agent WS broken — re-queue
                            handle_agent_disconnect(session, sessions_store)
                            await websocket.send_json({"type": "handoff_started", "reason": "Agent disconnected — re-queued"})
                else:
                    # === AI RESPONSE FLOW WITH RESILIENCE + TRACING ===
                    await websocket.send_json({"type": "thinking"})

                    # --- Start trace ---
                    trace = RequestTrace(
                        session_id=session_id,
                        user_matricule=session.get("user_matricule", ""),
                        query=content,
                    )
                    span_recv = trace.start_span("RECEIVED", message_length=len(content))
                    span_recv.finish()

                    # Use RAG pipeline (with circuit breaker + timeout)
                    from backend.services.rag_service import knowledge_store
                    if knowledge_store.count > 0:
                        span_rag = trace.start_span("RAG_SEARCH", store_count=knowledge_store.count)
                        ai_result = await get_rag_ai_response(content)
                        span_rag.finish(
                            similarity=ai_result.get("similarity"),
                            source=ai_result.get("source"),
                            degraded=ai_result.get("degraded", False),
                        )
                    else:
                        span_sim = trace.start_span("SIMULATED_RESPONSE")
                        await asyncio.sleep(1.0 + random.random())
                        ai_result = get_simulated_ai_response(content)
                        span_sim.finish()

                    # --- Evaluate & respond ---
                    span_eval = trace.start_span("LLM_EVAL", confidence=ai_result.get("confidence"))

                    # --- Handle degraded responses (timeout/circuit open) ---
                    if ai_result.get("degraded"):
                        span_eval.finish(status="degraded", failure_type=ai_result.get("failure_type"))
                        trace.finish("DEGRADED", confidence=0)

                        session["status"] = "handoff_pending"
                        session["reason"] = f"Service degradation ({ai_result.get('failure_type', 'unknown')})"
                        session["history"].append({
                            "role": "system",
                            "content": ai_result["text"],
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({
                            "type": "handoff_started",
                            "reason": session["reason"],
                            "degraded": True,
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

                    elif ai_result["confidence"] < 30 or ai_result["text"] is None:
                        span_eval.finish(status="low_confidence")
                        trace.finish("HUMAN_ESCALATED", confidence=ai_result["confidence"])

                        session["status"] = "handoff_pending"
                        session["reason"] = f"Low confidence ({ai_result['confidence']}%) on: {content[:50]}"
                        session["history"].append({
                            "role": "system",
                            "content": "Transfert vers un specialiste I-Way en cours...",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({"type": "handoff_started", "reason": session["reason"]})
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
                    else:
                        span_eval.finish(status="high_confidence")

                        # Stream AI response token by token
                        span_stream = trace.start_span("RESPONSE", confidence=ai_result["confidence"])
                        response_text = ai_result["text"]
                        words = response_text.split(" ")
                        for i, word in enumerate(words):
                            token = word + (" " if i < len(words) - 1 else "")
                            await websocket.send_json({"type": "ai_token", "token": token})
                            await asyncio.sleep(0.03 + random.random() * 0.05)

                        done_payload = {"type": "ai_done", "confidence": ai_result["confidence"]}
                        if ai_result.get("source"):
                            done_payload["source"] = ai_result["source"]
                        if ai_result.get("hitl_boosted"):
                            done_payload["hitl_boosted"] = True

                        await websocket.send_json(done_payload)
                        session["history"].append({
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": datetime.now().isoformat(),
                            "confidence": ai_result["confidence"],
                            "source": ai_result.get("source", "simulated"),
                        })
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
                user_ws = session.get("user_ws")
                if user_ws:
                    try:
                        await user_ws.send_json({"type": "agent_message", "content": content, "timestamp": agent_msg["timestamp"]})
                    except Exception:
                        handle_user_disconnect(session)

            elif msg_type == "manual_handoff_request":
                session["status"] = "handoff_pending"
                session["reason"] = "User manually requested a human agent"
                session["history"].append({
                    "role": "system",
                    "content": "Vous avez demande a parler a un agent humain. Transfert en cours...",
                    "timestamp": datetime.now().isoformat()
                })
                await websocket.send_json({"type": "handoff_started", "reason": session["reason"]})
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
                # Notify user that agent disconnected
                user_ws = session.get("user_ws")
                if user_ws:
                    try:
                        await user_ws.send_json({
                            "type": "agent_disconnected",
                            "message": "L'agent a ete deconnecte. Recherche d'un nouvel agent..."
                        })
                    except Exception:
                        pass
                # Broadcast re-queue to agent dashboard
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
        logger.info(f"Chat WS disconnected from session {session_id} (agent={is_agent})")

    except Exception as e:
        logger.error(f"Chat WS error in session {session_id}: {e}")
        if is_agent:
            handle_agent_disconnect(session, sessions_store)
        else:
            handle_user_disconnect(session)
