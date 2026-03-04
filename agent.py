"""
agent.py — LangGraph Stateful AI Agent for I-Santé.

Supports two LLM backends:
  • Cloud:  Gemini 2.5 Flash via langchain-google-genai  (default)
  • Local:  Qwen 3.5 9B via Ollama + langchain-openai

Toggle via env var:  USE_LOCAL_LLM=true  (defaults to false → Cloud/Gemini)

Run standalone:  python agent.py
Requires:        Mock Server on :8000  +  GOOGLE_API_KEY (cloud) or Ollama (local)
"""

import os
import httpx
from typing import Annotated
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from bot_tools import get_personal_dossiers, search_knowledge_base, escalate_to_human

# ── Configuration (loaded from .env) ───────────────────────────────

load_dotenv()

USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://localhost:8000")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

SYSTEM_PROMPT = """Tu es l'assistant virtuel I-Santé, l'assistant intelligent de la mutuelle I-Way Solutions.

RÈGLES STRICTES :
1. Tu parles TOUJOURS en français.
2. Tu ne dois JAMAIS inventer des informations. Si tu ne connais pas la réponse, utilise l'outil `escalate_to_human`.
3. Pour toute question sur les dossiers, contrats ou données personnelles de l'utilisateur, utilise l'outil `get_personal_dossiers` avec le matricule et le token fournis dans le contexte.
4. Pour toute question sur les règles, plafonds, remboursements ou procédures d'assurance, utilise l'outil `search_knowledge_base`.
5. Si l'utilisateur est mécontent, en colère, ou demande explicitement un agent humain, utilise IMMÉDIATEMENT l'outil `escalate_to_human`.
6. Tu peux utiliser PLUSIEURS outils en séquence pour répondre à une question complexe.
7. Sois professionnel, empathique et concis dans tes réponses.

CONTEXTE UTILISATEUR :
- Matricule : {matricule}
- Token d'authentification : {token}

Quand tu appelles les outils `get_personal_dossiers` ou `escalate_to_human`, utilise le matricule "{matricule}" et le token "{token}"."""


# ── Agent State ───────────────────────────────────────────────

class AgentState(TypedDict):
    """State carried through the LangGraph execution."""
    messages: Annotated[list[BaseMessage], add_messages]
    matricule: str
    token: str


# ── Graph Builder ─────────────────────────────────────────────

def build_agent_graph():
    """Construct and compile the LangGraph agent."""

    # LLM — toggle between Cloud (Gemini) and Local (Ollama/Qwen)
    if USE_LOCAL_LLM:
        llm = ChatOpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",
            model=OLLAMA_MODEL,
            temperature=0,
        )
        mode_label = "LOCAL / Qwen 3.5 (Ollama)"
    else:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
        )
        mode_label = "CLOUD / Gemini 2.5 Flash"

    # Tools — binding works identically for both backends
    tools = [get_personal_dossiers, search_knowledge_base, escalate_to_human]
    llm_with_tools = llm.bind_tools(tools)

    # ── Node: Chatbot ─────────────────────────────────────────
    def chatbot_node(state: AgentState) -> dict:
        """Invoke the LLM with system prompt + conversation history."""
        matricule = state["matricule"]
        token = state["token"]

        # Build the system message with user context injected
        sys_msg = SystemMessage(
            content=SYSTEM_PROMPT.format(matricule=matricule, token=token)
        )

        # Prepend system message to the conversation
        messages_with_system = [sys_msg] + state["messages"]

        # Invoke the LLM
        response = llm_with_tools.invoke(messages_with_system)
        return {"messages": [response]}

    # ── Routing ───────────────────────────────────────────────
    def should_use_tools(state: AgentState) -> str:
        """Route to ToolNode if the last message has tool_calls, else END."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # ── Build Graph ───────────────────────────────────────────
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("chatbot", chatbot_node)
    graph.add_node("tools", ToolNode(tools=tools))

    # Edges
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", should_use_tools, {"tools": "tools", END: END})
    graph.add_edge("tools", "chatbot")

    compiled = graph.compile()
    compiled.mode_label = mode_label  # attach for display
    return compiled


# ── Helper: Login to Mock Server ──────────────────────────────

def login_to_mock_server(matricule: str, password: str) -> str:
    """Authenticate against the local Mock Server, return the JWT."""
    resp = httpx.post(
        f"{MOCK_SERVER_URL}/auth/login",
        json={"matricule": matricule, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


# ── Main: Interactive Test ────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Verify prerequisites
    if USE_LOCAL_LLM:
        print("🚀 STARTING AI CHATBOT [Mode: LOCAL / QWEN 3.5 via Ollama]")
        print("   Ensure Ollama is running: ollama serve")
        print("   Ensure model is pulled: ollama pull qwen3.5:9b")
    else:
        print("🚀 STARTING AI CHATBOT [Mode: CLOUD / GEMINI 2.5 Flash]")
        if not os.environ.get("GOOGLE_API_KEY"):
            print("❌ GOOGLE_API_KEY not found in environment.")
            print("   Set it with:  $env:GOOGLE_API_KEY = 'your-key-here'")
            sys.exit(1)

    # Step 1 — Login as Nadia
    print("🔐 Logging in as Nadia (12345)...")
    try:
        token = login_to_mock_server("12345", "pass")
        print(f"✅ Token obtained: {token[:40]}...")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        print("   Make sure the Mock Server is running: python main.py")
        sys.exit(1)

    # Step 2 — Build the agent
    print("🤖 Building LangGraph agent...")
    agent = build_agent_graph()

    # Step 3 — Run a test query
    test_query = "Quels sont mes dossiers en cours et quel est le plafond dentaire ?"
    print(f"\n📩 User query: {test_query}\n")
    print("─" * 60)

    initial_state = {
        "messages": [HumanMessage(content=test_query)],
        "matricule": "12345",
        "token": token,
    }

    # Stream the agent execution
    for event in agent.stream(initial_state, stream_mode="values"):
        messages = event.get("messages", [])
        if messages:
            last = messages[-1]
            # Print tool calls
            if hasattr(last, "tool_calls") and last.tool_calls:
                for tc in last.tool_calls:
                    print(f"🔧 Tool call: {tc['name']}({tc['args']})")
            # Print tool results
            elif last.type == "tool":
                print(f"📦 Tool result [{last.name}]: {last.content[:120]}...")
            # Print final AI response
            elif isinstance(last, AIMessage) and last.content:
                print(f"\n🤖 Assistant:\n{last.content}")

    print("\n" + "─" * 60)
    print("✅ Agent execution complete.")
