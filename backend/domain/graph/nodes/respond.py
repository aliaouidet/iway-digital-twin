"""
Node 8: Respond — Final response delivery.

Packages the final response as an AIMessage and appends it to
the conversation history. Terminal node before END.
"""

import logging

from langchain_core.messages import AIMessage

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


async def respond_node(state: ClaimsGraphState) -> dict:
    """
    Node 8: Final Response Delivery.

    Reads final_response (from clarification/handoff/escalation/stall)
    or draft_response (from the main flow) and wraps it as an AIMessage.
    """
    response_text = (
        state.get("final_response")
        or state.get("draft_response")
        or "Je suis desole, je n'ai pas pu traiter votre demande."
    )

    logger.info(f"Responding ({len(response_text)} chars)")

    return {
        "messages": [AIMessage(content=response_text)],
    }
