"""
Chat Service — Per-session WebSocket handler with LangGraph Agent + Resilience.

Architecture:
  PRIMARY PATH:  LangGraph Agent (Gemini/Ollama LLM + BotTools)
  FALLBACK PATH: RAG-only similarity lookup (no LLM reasoning)

Resilience features:
- Agent initialization failure → graceful fallback to RAG-only
- LLM timeout → auto-escalate to human agent
- Circuit breaker → prevents cascading LLM/embedding failures
- Agent disconnect → re-queues session for another agent
- User disconnect → preserves state for reconnection
- Graceful degradation → fallback responses when services are down
- Per-session locks → prevent race conditions on concurrent mutations
- Sliding window → prevents LLM context window overflow
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

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# --- Per-session asyncio locks to prevent concurrent mutation ---
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

def get_session_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session lock for safe concurrent access."""
    return _session_locks[session_id]


async def _persist_message(
    session_id: str,
    role: str,
    content: str,
    confidence: float = None,
    model_used: str = None,
):
    """Fire-and-forget message persistence to PostgreSQL."""
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import save_message

        async with async_session_factory() as db:
            await save_message(db, session_id, role, content, confidence, model_used)
            await db.commit()
    except Exception as e:
        logger.debug(f"Message DB persist skipped: {e}")


# ==============================================================
# LANGGRAPH AGENT (lazy-loaded to avoid startup failure)
# ==============================================================

_shared_agent = None
_agent_available = False


def _get_agent():
    """Lazy-load the LangGraph agent. Returns None if unavailable."""
    global _shared_agent, _agent_available
    if _shared_agent is not None:
        return _shared_agent
    if not _agent_available and _shared_agent is None:
        try:
            from agent import build_agent_graph
            _shared_agent = build_agent_graph()
            _agent_available = True
            logger.info("🤖 LangGraph Agent loaded successfully")
        except Exception as e:
            _agent_available = False
            logger.warning(f"⚠️ LangGraph Agent unavailable (falling back to RAG-only): {e}")
    return _shared_agent


# ==============================================================
# AGENTIC AI RESPONSE (Primary Path — LangGraph + Tools)
# ==============================================================

async def get_agent_response(query: str, session: dict, websocket: WebSocket, handoff_mode: bool = False) -> dict:
    """
    Generate a response using the full LangGraph agent with tool calling.
    
    When handoff_mode=True, the agent uses an empathetic tone acknowledging
    that a human agent is on the way.
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    agent = _get_agent()
    if agent is None:
        return None  # Signal to caller to use fallback

    # Build messages with sliding window to prevent context overflow
    lc_history = _build_agent_messages(session, handoff_mode=handoff_mode)
    
    initial_state = {
        "messages": lc_history,
        "matricule": session.get("user_matricule", "12345"),
        "token": session.get("user_token", ""),
    }
    config = {"configurable": {"thread_id": f"ws-session-{session['id']}"}}

    full_response = ""
    tools_called = []

    try:
        async for event in agent.astream_events(initial_state, config=config, version="v1"):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    # Only stream final response tokens (not intermediate reasoning)
                    # Check if we're in the final chatbot node
                    if not (hasattr(chunk, "tool_calls") and chunk.tool_calls):
                        full_response += chunk.content
                        await websocket.send_json({"type": "ai_token", "token": chunk.content})

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tools_called.append(tool_name)
                # Show user what tool is being called
                tool_labels = {
                    "search_knowledge_base": "🔍 Recherche dans la base de connaissances...",
                    "get_personal_dossiers": "📋 Consultation de vos dossiers...",
                    "escalate_to_human": "👤 Transfert vers un agent...",
                    "analyze_medical_receipt": "🧾 Analyse de la facture médicale...",
                }
                status_text = tool_labels.get(tool_name, f"⚙️ {tool_name}...")
                await websocket.send_json({"type": "thinking", "status": status_text})

            elif kind == "on_tool_end":
                pass  # Tool results are processed by the agent internally

        if full_response.strip():
            return {
                "text": full_response.strip(),
                "confidence": 90,  # Agent responses are generally high-confidence
                "source": "langgraph_agent",
                "tools_called": tools_called,
                "degraded": False,
            }
        else:
            return None  # Empty response — fall back

    except Exception as e:
        logger.error(f"❌ Agent execution failed: {e}")
        llm_circuit.record_failure()
        return None  # Signal fallback


# ==============================================================
# SLIDING WINDOW — Prevents LLM context overflow
# ==============================================================

def _build_agent_messages(session: dict, handoff_mode: bool = False, max_turns: int = 10):
    """Build LangChain messages with a sliding window to prevent context overflow.
    
    Keeps the most recent `max_turns` user/assistant exchanges.
    Always preserves the first user message for context anchoring.
    Truncates long assistant responses (tool results can be huge JSON).
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    lc_history = []

    if handoff_mode:
        lc_history.append(SystemMessage(content=(
            "IMPORTANT: Un agent humain est en route pour aider le client. "
            "Adopte un ton empathique et rassurant. "
            "Aide autant que possible en attendant l'agent."
        )))

    # Filter to user/assistant messages only (skip system messages)
    chat_messages = [h for h in session.get("history", []) if h["role"] in ("user", "assistant")]
    
    # Sliding window: keep first message + last N messages
    if len(chat_messages) > max_turns * 2:
        windowed = chat_messages[:1] + chat_messages[-(max_turns * 2 - 1):]
    else:
        windowed = chat_messages

    for h in windowed:
        if h["role"] == "user":
            lc_history.append(HumanMessage(content=h["content"]))
        elif h["role"] == "assistant":
            # Truncate long assistant responses (tool results can be huge)
            content = h["content"][:2000] if len(h["content"]) > 2000 else h["content"]
            lc_history.append(AIMessage(content=content))

    return lc_history


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
                    # ═══ HYBRID HANDOFF: AI continues with empathetic tone ═══
                    await websocket.send_json({"type": "thinking", "status": "Réflexion en cours..."})

                    trace = RequestTrace(
                        session_id=session_id,
                        user_matricule=session.get("user_matricule", ""),
                        query=content,
                    )
                    span_recv = trace.start_span("RECEIVED", message_length=len(content))
                    span_recv.finish()

                    ai_result = None

                    # Try agent first, then RAG, then simulated — same 3-tier
                    if llm_circuit.can_execute():
                        span_agent = trace.start_span("HANDOFF_AI_RESPONSE")
                        try:
                            ai_result = await asyncio.wait_for(
                                get_agent_response(content, session, websocket, handoff_mode=True),
                                timeout=settings.LLM_TIMEOUT_SECONDS + 10
                            )
                            if ai_result:
                                span_agent.finish(source="langgraph_agent_handoff")
                                llm_circuit.record_success()
                            else:
                                span_agent.finish(status="agent_unavailable")
                        except asyncio.TimeoutError:
                            span_agent.finish(status="timeout")
                            llm_circuit.record_failure()
                        except Exception as e:
                            span_agent.finish(status="error", error=str(e))

                    if ai_result is None:
                        from backend.services.rag_service import knowledge_store
                        if knowledge_store.count > 0:
                            ai_result = await get_rag_ai_response(content)
                        else:
                            await asyncio.sleep(0.3 + random.random() * 0.3)
                            ai_result = get_simulated_ai_response(content)

                    # Send response with handoff_ai flag
                    if ai_result and ai_result.get("text"):
                        response_text = ai_result["text"]
                        confidence = ai_result.get("confidence", 50)

                        # Stream tokens if not already streamed by agent
                        if ai_result.get("source") != "langgraph_agent":
                            words = response_text.split(" ")
                            for i, word in enumerate(words):
                                token = word + (" " if i < len(words) - 1 else "")
                                await websocket.send_json({"type": "ai_token", "token": token})
                                await asyncio.sleep(0.03 + random.random() * 0.05)

                        await websocket.send_json({
                            "type": "ai_done",
                            "confidence": confidence,
                            "is_handoff_ai": True,  # UI shows badge
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

                        trace.finish("HANDOFF_AI_RESOLVED", confidence=confidence)
                    else:
                        await websocket.send_json({
                            "type": "ai_done",
                            "confidence": 0,
                            "is_handoff_ai": True,
                            "text": "Je comprends votre frustration. Un agent va vous répondre très bientôt.",
                        })
                        trace.finish("HANDOFF_AI_FALLBACK", confidence=0)

                    trace_store.add(trace)
                    await broadcast_trace(trace)

                else:
                    # === NORMAL AI RESPONSE FLOW (session.status == "active") ===
                    await websocket.send_json({"type": "thinking"})

                    # --- Start trace ---
                    trace = RequestTrace(
                        session_id=session_id,
                        user_matricule=session.get("user_matricule", ""),
                        query=content,
                    )
                    span_recv = trace.start_span("RECEIVED", message_length=len(content))
                    span_recv.finish()

                    ai_result = None

                    # ── TIER 1: LangGraph Agent (primary) ──
                    if llm_circuit.can_execute():
                        span_agent = trace.start_span("AGENT_EXECUTION")
                        try:
                            ai_result = await asyncio.wait_for(
                                get_agent_response(content, session, websocket),
                                timeout=settings.LLM_TIMEOUT_SECONDS + 10
                            )
                            if ai_result:
                                span_agent.finish(
                                    tools=ai_result.get("tools_called", []),
                                    source="langgraph_agent",
                                )
                                llm_circuit.record_success()
                            else:
                                span_agent.finish(status="agent_unavailable")
                        except asyncio.TimeoutError:
                            span_agent.finish(status="timeout")
                            llm_circuit.record_failure()
                            logger.warning("⏰ Agent timed out — falling back to RAG")
                        except Exception as e:
                            span_agent.finish(status="error", error=str(e))
                            logger.warning(f"⚠️ Agent error: {e} — falling back to RAG")

                    # ── TIER 2: RAG-only fallback ──
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
                            # ── TIER 3: Simulated response (no RAG store) ──
                            span_sim = trace.start_span("SIMULATED_RESPONSE")
                            await asyncio.sleep(0.5 + random.random() * 0.5)
                            ai_result = get_simulated_ai_response(content)
                            span_sim.finish()

                    # --- Evaluate & respond ---
                    span_eval = trace.start_span("EVAL", confidence=ai_result.get("confidence"))

                    # Handle agent-streamed responses (already sent tokens)
                    if ai_result.get("source") == "langgraph_agent":
                        tools_called = ai_result.get("tools_called", [])

                        # ═══ ESCALATION INTERCEPT ═══
                        # If the agent called escalate_to_human, we must actually
                        # transition the session to handoff_pending — not just
                        # send a text response.
                        if "escalate_to_human" in tools_called:
                            span_eval.finish(status="escalation_intercepted")

                            # Store AI response in history
                            async with lock:
                                session["history"].append({
                                    "role": "assistant",
                                    "content": ai_result["text"],
                                    "timestamp": datetime.now().isoformat(),
                                    "confidence": ai_result["confidence"],
                                    "source": "langgraph_agent",
                                })
                                asyncio.create_task(_persist_message(
                                    session_id, "assistant", ai_result["text"],
                                    confidence=ai_result["confidence"], model_used="langgraph_agent"
                                ))

                                # Transition session state
                                session["status"] = "handoff_pending"
                                session["reason"] = f"Agent tool escalation: {content[:80]}"
                                session["trigger_message"] = {
                                    "content": ai_result["text"],
                                    "confidence": ai_result["confidence"],
                                    "query": content,
                                }
                                session["last_ai_confidence"] = ai_result["confidence"]

                                sys_msg = "Un agent humain va vous rejoindre bientôt. Vous pouvez continuer à poser des questions en attendant."
                                session["history"].append({
                                    "role": "system",
                                    "content": sys_msg,
                                    "timestamp": datetime.now().isoformat(),
                                })
                                asyncio.create_task(_persist_message(session_id, "system", sys_msg))

                            # Tell the user the handoff is happening
                            await websocket.send_json({
                                "type": "ai_done",
                                "confidence": ai_result["confidence"],
                                "source": "langgraph_agent",
                                "tools_called": tools_called,
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
                                }
                            })

                            # Persist status change to DB
                            asyncio.create_task(_persist_escalation(
                                session_id, session["reason"]
                            ))

                            trace.finish(
                                "HUMAN_ESCALATED",
                                confidence=ai_result["confidence"],
                                source_type="langgraph_agent",
                            )
                        else:
                            # ═══ NORMAL AGENT RESOLVED ═══
                            span_eval.finish(status="agent_resolved")
                            await websocket.send_json({
                                "type": "ai_done",
                                "confidence": ai_result["confidence"],
                                "source": "langgraph_agent",
                                "tools_called": tools_called,
                            })
                            session["history"].append({
                                "role": "assistant",
                                "content": ai_result["text"],
                                "timestamp": datetime.now().isoformat(),
                                "confidence": ai_result["confidence"],
                                "source": "langgraph_agent",
                            })
                            asyncio.create_task(_persist_message(
                                session_id, "assistant", ai_result["text"],
                                confidence=ai_result["confidence"], model_used="langgraph_agent"
                            ))
                            session["last_ai_confidence"] = ai_result["confidence"]
                            trace.finish(
                                "AGENT_RESOLVED",
                                confidence=ai_result["confidence"],
                                source_type="langgraph_agent",
                            )

                    # Handle degraded responses (timeout/circuit open)
                    elif ai_result.get("degraded"):
                        span_eval.finish(status="degraded", failure_type=ai_result.get("failure_type"))
                        trace.finish("DEGRADED", confidence=0)

                        # Store trigger message
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

                        # Store the trigger message for agent review
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

                        done_payload = {"type": "ai_done", "confidence": ai_result["confidence"]}
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
        logger.info(f"Chat WS disconnected from session {session_id} (agent={is_agent})")

    except Exception as e:
        logger.error(f"Chat WS error in session {session_id}: {e}")
        if is_agent:
            handle_agent_disconnect(session, sessions_store)
        else:
            handle_user_disconnect(session)


async def _persist_escalation(session_id: str, reason: str):
    """Fire-and-forget: persist escalation status change to PostgreSQL."""
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import update_session_status

        async with async_session_factory() as db:
            await update_session_status(
                db, session_id, "handoff_pending",
                reason=reason,
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"Escalation DB persist skipped: {e}")

