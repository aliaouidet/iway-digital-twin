"""
Message Persister — Fire-and-forget persistence to PostgreSQL.

Handles:
  - Message persistence (user, assistant, agent, system messages)
  - Escalation status updates
  - Sliding window context management

Extracted from chat_service.py to follow SRP (system-design skill).
"""

import logging

logger = logging.getLogger("I-Way-Twin")


async def persist_message(
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


async def persist_escalation(session_id: str, reason: str):
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


def build_agent_messages(session: dict, handoff_mode: bool = False, max_turns: int = 10):
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
