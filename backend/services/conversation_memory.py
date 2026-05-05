"""
Conversation Memory — Summary buffer for multi-turn coherence.

Provides conversation context to the LLM by:
  1. Keeping the last N messages verbatim (recent context)
  2. Summarizing older messages into a rolling context block (history)

This is a lightweight, extraction-based summarizer — no LLM call needed.

Usage:
    from backend.services.conversation_memory import build_conversation_context
    context = build_conversation_context(messages, max_recent=3)
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger("I-Way-Twin")


def build_conversation_context(
    messages: List[Dict[str, Any]],
    max_recent: int = 3,
    max_summary_messages: int = 10,
) -> str:
    """
    Build a conversation context string for LLM prompt injection.

    Strategy:
      - Last `max_recent` messages are included verbatim
      - Older messages (up to `max_summary_messages`) are compressed
        into a brief summary

    Args:
        messages: List of {role, content, timestamp, ...} dicts
        max_recent: Number of recent messages to include verbatim
        max_summary_messages: Max older messages to summarize

    Returns:
        Formatted context string ready for system prompt injection
    """
    if not messages:
        return ""

    # Filter to only user/assistant messages (skip system messages)
    relevant = [
        m for m in messages
        if m.get("role") in ("user", "assistant", "agent")
    ]

    if not relevant:
        return ""

    # Split into recent and older
    recent = relevant[-max_recent:] if len(relevant) > max_recent else relevant
    older = relevant[:-max_recent] if len(relevant) > max_recent else []

    parts = []

    # Build summary of older messages
    if older:
        # Take the most recent N older messages
        to_summarize = older[-max_summary_messages:]
        summary = _extract_summary(to_summarize)
        if summary:
            parts.append(f"RÉSUMÉ DE LA CONVERSATION PRÉCÉDENTE:\n{summary}")

    # Build verbatim recent messages
    if recent:
        recent_lines = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                recent_lines.append(f"Utilisateur: {content}")
            elif role == "assistant":
                recent_lines.append(f"I-Santé: {content}")
            elif role == "agent":
                recent_lines.append(f"Agent humain: {content}")

        if recent_lines:
            parts.append("DERNIERS ÉCHANGES:\n" + "\n".join(recent_lines))

    return "\n\n".join(parts)


def _extract_summary(messages: List[Dict[str, Any]]) -> str:
    """
    Extract a brief summary from older messages without using an LLM.

    Strategy: Extract the key topics discussed by looking at user messages
    and noting what the assistant addressed.
    """
    if not messages:
        return ""

    user_topics = []
    assistant_actions = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()

        if not content:
            continue

        if role == "user":
            # Keep first 80 chars of each user message as a topic
            user_topics.append(content[:80])
        elif role == "assistant":
            # Extract the gist of the assistant's response
            first_sentence = content.split(".")[0][:100]
            if first_sentence:
                assistant_actions.append(first_sentence)

    summary_parts = []
    if user_topics:
        topics_text = "; ".join(user_topics[:5])  # Max 5 topics
        summary_parts.append(f"L'utilisateur a posé des questions sur: {topics_text}")

    if assistant_actions:
        actions_text = "; ".join(assistant_actions[:3])  # Max 3 actions
        summary_parts.append(f"L'assistant a répondu: {actions_text}")

    return ". ".join(summary_parts) + "." if summary_parts else ""
