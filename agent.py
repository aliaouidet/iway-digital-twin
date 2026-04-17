"""
agent.py — LangGraph Stateful AI Agent for I-Santé.

Supports two LLM backends:
  • Cloud:  Gemini 2.5 Flash via langchain-google-genai  (default)
  • Local:  Qwen 3.5 9B via Ollama + langchain-openai

Security: JWT tokens are NEVER exposed to the LLM. They are injected from
AgentState into tool calls at runtime by the custom tool_executor node.

Toggle via env var:  USE_LOCAL_LLM=true  (defaults to false → Cloud/Gemini)

Run standalone:  python agent.py
Requires:        Mock Server on :8000  +  GOOGLE_API_KEY (cloud) or Ollama (local)
"""

import os
import logging
import inspect
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
    ToolMessage,
)
from langchain_core.tools import InjectedToolArg
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from bot_tools import (
    get_personal_dossiers,
    search_knowledge_base,
    escalate_to_human,
    analyze_medical_receipt,
)

# ── Configuration (loaded from .env) ───────────────────────────────

load_dotenv()

USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
try:
    from backend.config import get_settings as _get_settings
    _settings = _get_settings()
    MOCK_SERVER_URL = _settings.MOCK_SERVER_URL
    OLLAMA_BASE_URL = _settings.OLLAMA_BASE_URL
    OLLAMA_MODEL = _settings.OLLAMA_MODEL
except Exception:
    MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://localhost:8000")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

SYSTEM_PROMPT = """Tu es l'assistant virtuel I-Santé, l'assistant intelligent de la mutuelle I-Way Solutions.

RÈGLES STRICTES :
1. Tu parles TOUJOURS en français.
2. Tu ne dois JAMAIS inventer des informations. Si tu ne connais pas la réponse, utilise l'outil `escalate_to_human`.
3. Pour toute question sur les dossiers, contrats ou données personnelles de l'utilisateur, utilise l'outil `get_personal_dossiers`. Les identifiants sont injectés automatiquement — tu n'as PAS besoin de les fournir.
4. Pour toute question sur les règles, plafonds, remboursements ou procédures d'assurance, utilise l'outil `search_knowledge_base`.
5. Si l'utilisateur est mécontent, en colère, ou demande explicitement un agent humain, utilise IMMÉDIATEMENT l'outil `escalate_to_human` avec une description du problème.
6. Tu peux utiliser PLUSIEURS outils en séquence pour répondre à une question complexe.
7. Sois professionnel, empathique et concis dans tes réponses.
8. Si l'utilisateur fournit une facture ou un reçu médical (image), utilise l'outil `analyze_medical_receipt` pour extraire les données (prestataire, montant, acte). Ensuite, utilise `search_knowledge_base` pour vérifier le taux de remboursement de cet acte, et enfin, calcule le montant estimé du remboursement pour l'utilisateur.

CONTEXTE UTILISATEUR :
- Matricule : {matricule}
- L'authentification est gérée automatiquement par le système."""


# ── Agent State ───────────────────────────────────────────────

class AgentState(TypedDict):
    """State carried through the LangGraph execution."""
    messages: Annotated[list[BaseMessage], add_messages]
    matricule: str
    token: str


# ── Tool Registry & Injection ────────────────────────────────

TOOLS = [get_personal_dossiers, search_knowledge_base, escalate_to_human, analyze_medical_receipt]
TOOL_MAP = {t.name: t for t in TOOLS}

# Pre-compute which tools need injected params (InjectedToolArg)
_INJECTABLE_PARAMS = {}
for _tool in TOOLS:
    # Async tools store the callable in .coroutine, sync tools in .func
    _callable = getattr(_tool, "coroutine", None) or getattr(_tool, "func", None) or _tool
    _sig = inspect.signature(_callable)
    _injectables = set()
    for _name, _param in _sig.parameters.items():
        _annotation = _param.annotation
        # Check if the annotation uses Annotated[str, InjectedToolArg]
        if hasattr(_annotation, "__metadata__"):
            for _meta in _annotation.__metadata__:
                if isinstance(_meta, type) and issubclass(_meta, InjectedToolArg):
                    _injectables.add(_name)
                elif isinstance(_meta, InjectedToolArg):
                    _injectables.add(_name)
    _INJECTABLE_PARAMS[_tool.name] = _injectables


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

    logger_agent = logging.getLogger("I-Way-Twin")
    logger_agent.info(f"⚡ LLM initialized: {mode_label}")

    # Tools — binding works identically for both backends
    llm_with_tools = llm.bind_tools(TOOLS)

    # ── Node: Chatbot ─────────────────────────────────────────
    async def chatbot_node(state: AgentState) -> dict:
        """Invoke the LLM with system prompt + conversation history."""
        matricule = state["matricule"]

        # Build the system message — token is NOT included
        sys_msg = SystemMessage(
            content=SYSTEM_PROMPT.format(matricule=matricule)
        )

        # Prepend system message to the conversation
        messages_with_system = [sys_msg] + state["messages"]

        # Invoke the LLM asynchronously (enables token streaming via astream_events)
        response = await llm_with_tools.ainvoke(messages_with_system)
        return {"messages": [response]}

    # ── Node: Tool Executor (secure injection) ────────────────
    async def tool_executor(state: AgentState) -> dict:
        """Execute tool calls with token/matricule injected from state.

        This node replaces the standard ToolNode. It reads the last
        AIMessage's tool_calls, injects InjectedToolArg values from
        AgentState, and returns ToolMessages with results.
        """
        last_msg = state["messages"][-1]
        results: list[ToolMessage] = []

        # State values available for injection
        inject_values = {
            "matricule": state.get("matricule", ""),
            "token": state.get("token", ""),
        }

        for tc in last_msg.tool_calls:
            tool_name = tc["name"]
            tool_fn = TOOL_MAP.get(tool_name)

            if tool_fn is None:
                results.append(ToolMessage(
                    content=f"Erreur: outil '{tool_name}' introuvable.",
                    tool_call_id=tc["id"],
                    name=tool_name,
                ))
                continue

            # Merge LLM-provided args with injected state values
            args = dict(tc["args"])
            for param_name in _INJECTABLE_PARAMS.get(tool_name, set()):
                if param_name in inject_values:
                    args[param_name] = inject_values[param_name]

            try:
                result = await tool_fn.ainvoke(args)
            except Exception as e:
                result = f"Erreur lors de l'exécution de {tool_name}: {e}"

            results.append(ToolMessage(
                content=str(result),
                tool_call_id=tc["id"],
                name=tool_name,
            ))

        return {"messages": results}

    # ── Routing ───────────────────────────────────────────────
    def should_use_tools(state: AgentState) -> str:
        """Route to tool_executor if the last message has tool_calls, else END."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # ── Build Graph ───────────────────────────────────────────
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("chatbot", chatbot_node)
    graph.add_node("tools", tool_executor)

    # Edges
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", should_use_tools, {"tools": "tools", END: END})
    graph.add_edge("tools", "chatbot")

    compiled = graph.compile(checkpointer=MemorySaver())
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
        print("STARTING AI CHATBOT [Mode: LOCAL / QWEN 3.5 via Ollama]")
        print("   Ensure Ollama is running: ollama serve")
        print("   Ensure model is pulled: ollama pull qwen3.5:9b")
    else:
        print("STARTING AI CHATBOT [Mode: CLOUD / GEMINI 2.5 Flash]")
        if not os.environ.get("GOOGLE_API_KEY"):
            print("ERROR: GOOGLE_API_KEY not found in environment.")
            print("   Set it with:  $env:GOOGLE_API_KEY = 'your-key-here'")
            sys.exit(1)

    # Step 1 — Login as Nadia
    print("Logging in as Nadia (12345)...")
    try:
        token = login_to_mock_server("12345", "pass")
        print(f"Token obtained: {token[:40]}...")
    except Exception as e:
        print(f"Login failed: {e}")
        print("   Make sure the Mock Server is running: python main.py")
        sys.exit(1)

    # Step 2 — Build the agent
    print("Building LangGraph agent...")
    agent = build_agent_graph()

    # Step 3 — Run a test query
    test_query = "Quels sont mes dossiers en cours et quel est le plafond dentaire ?"
    print(f"\nUser query: {test_query}\n")
    print("-" * 60)

    initial_state = {
        "messages": [HumanMessage(content=test_query)],
        "matricule": "12345",
        "token": token,
    }
    config = {"configurable": {"thread_id": "test-session-1"}}

    # Stream the agent execution
    for event in agent.stream(initial_state, config=config, stream_mode="values"):
        messages = event.get("messages", [])
        if messages:
            last = messages[-1]
            # Print tool calls
            if hasattr(last, "tool_calls") and last.tool_calls:
                for tc in last.tool_calls:
                    print(f"[Tool call] {tc['name']}({tc['args']})")
            # Print tool results
            elif last.type == "tool":
                print(f"[Tool result: {last.name}] {last.content[:120]}...")
            # Print final AI response
            elif isinstance(last, AIMessage) and last.content:
                print(f"\nAssistant:\n{last.content}")

    print("\n" + "-" * 60)
    print("Agent execution complete.")
