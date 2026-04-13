"""
chat_ui.py — Streamlit Chat UI for the I-Sante Virtual Assistant.

Run:   streamlit run chat_ui.py
Requires: Mock Server running on :8000  (python main.py)
"""

import os
import uuid
import time
import json
import base64
import asyncio
import threading
import queue as queue_module
import requests
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from agent import build_agent_graph, MOCK_SERVER_URL, USE_LOCAL_LLM, OLLAMA_MODEL

load_dotenv()

# ── Page Config ───────────────────────────────────────────────

st.set_page_config(
    page_title="I-Sante Assistant",
    page_icon="I",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Modern Styling ────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* --- Global --- */
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    .block-container {
        max-width: 100% !important;
        padding: 1rem 2.5rem !important;
    }

    /* --- Sidebar --- */
    [data-testid="stSidebarContent"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
        padding-top: 0.5rem;
    }
    [data-testid="stSidebarContent"] .stMarkdown p,
    [data-testid="stSidebarContent"] .stMarkdown li,
    [data-testid="stSidebarContent"] .stCaption p {
        color: #94a3b8 !important;
    }
    [data-testid="stSidebarContent"] h1,
    [data-testid="stSidebarContent"] h2,
    [data-testid="stSidebarContent"] h3,
    [data-testid="stSidebarContent"] h4,
    [data-testid="stSidebarContent"] h5 {
        color: #f1f5f9 !important;
    }
    [data-testid="stSidebarContent"] hr {
        border-color: #334155;
    }
    section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }

    /* --- Sidebar buttons: force readable text --- */
    [data-testid="stSidebarContent"] .stButton > button {
        background: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #334155 !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
        transition: all 0.15s ease;
    }
    [data-testid="stSidebarContent"] .stButton > button:hover {
        background: #e2e8f0 !important;
        color: #0f172a !important;
        border-color: #64748b !important;
    }
    [data-testid="stSidebarContent"] .stButton > button p {
        color: #0f172a !important;
    }
    [data-testid="stSidebarContent"] .stDownloadButton > button {
        background: #1e3a5f !important;
        color: #e2e8f0 !important;
        border: 1px solid #334155 !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebarContent"] .stDownloadButton > button:hover {
        background: #2563eb !important;
    }
    [data-testid="stSidebarContent"] .stDownloadButton > button p {
        color: #e2e8f0 !important;
    }

    /* --- Sidebar metric values --- */
    [data-testid="stSidebarContent"] [data-testid="stMetricValue"] {
        color: #f1f5f9 !important;
    }
    [data-testid="stSidebarContent"] [data-testid="stMetricLabel"] p {
        color: #94a3b8 !important;
    }

    /* --- Header --- */
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #2563eb 100%);
        border-radius: 16px;
        padding: 1.8rem 2.5rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 4px 24px rgba(37,99,235,0.15);
    }
    .main-header .title {
        color: #ffffff;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .main-header .subtitle {
        color: #93c5fd;
        font-size: 0.85rem;
        font-weight: 400;
        margin-top: 4px;
    }
    .header-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .badge-cloud {
        background: rgba(34,197,94,0.15);
        color: #4ade80;
        border: 1px solid rgba(34,197,94,0.3);
    }
    .badge-local {
        background: rgba(251,191,36,0.15);
        color: #fbbf24;
        border: 1px solid rgba(251,191,36,0.3);
    }
    .badge-user {
        background: rgba(255,255,255,0.1);
        color: #e2e8f0;
        border: 1px solid rgba(255,255,255,0.15);
        font-size: 0.75rem;
        padding: 4px 12px;
        border-radius: 20px;
    }

    /* --- Metrics --- */
    .metrics-strip {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-pill {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.7rem 1.2rem;
        flex: 1;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .metric-pill .metric-icon {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        color: white;
        font-weight: 700;
    }
    .metric-pill .metric-data .metric-value {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.2;
    }
    .metric-pill .metric-data .metric-label {
        font-size: 0.68rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .icon-blue { background: linear-gradient(135deg, #3b82f6, #2563eb); }
    .icon-green { background: linear-gradient(135deg, #22c55e, #16a34a); }
    .icon-purple { background: linear-gradient(135deg, #a855f7, #7c3aed); }

    /* --- Quick Actions --- */
    .quick-section {
        margin-bottom: 1.5rem;
    }
    .quick-label {
        font-size: 0.8rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        margin-bottom: 0.6rem;
    }

    /* --- Tool trace --- */
    .tool-trace-block {
        background: #f0f9ff;
        border-left: 3px solid #3b82f6;
        padding: 0.6rem 1rem;
        margin: 0.3rem 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.82rem;
        font-family: 'Inter', sans-serif;
    }
    .tool-trace-block .tool-label {
        font-weight: 600;
        color: #2563eb;
    }

    /* --- Message timestamps --- */
    .ts {
        font-size: 0.65rem;
        color: #94a3b8;
        text-align: right;
        margin-top: 2px;
    }

    /* --- Welcome card --- */
    .welcome-card {
        background: linear-gradient(135deg, #f8fafc, #f1f5f9);
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 2.5rem;
        text-align: center;
        margin: 2rem auto;
        max-width: 700px;
    }
    .welcome-card h3 {
        color: #0f172a;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .welcome-card p {
        color: #64748b;
        font-size: 0.95rem;
    }
    .welcome-card table {
        margin: 1.2rem auto;
        text-align: left;
    }

    /* --- Hide streamlit branding --- */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)

# ── Session State Init ────────────────────────────────────────

defaults = {
    "messages": [],
    "token": None,
    "matricule": None,
    "user_name": None,
    "user_role": None,
    "agent": None,
    "thread_id": None,
    "streaming": False,
    "response_times": [],
    "tool_calls_count": 0,
    "turn_count": 0,
    "timestamps": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, list) else list(v)


# ── Cached Agent (only loads model once) ──────────────────────

@st.cache_resource(show_spinner="Loading AI model...")
def get_cached_agent():
    """Build and cache the agent graph + pre-warm RAG model (called once)."""
    import rag_engine
    print("[INIT] Loading RAG engine (sentence-transformers model)...", flush=True)
    rag_engine.get_engine()  # Pre-load sentence-transformers model
    print("[INIT] Building LangGraph agent...", flush=True)
    agent = build_agent_graph()
    print("[INIT] Agent ready!", flush=True)
    return agent


# ── Helpers ───────────────────────────────────────────────────

def do_login(matricule: str, password: str):
    try:
        resp = requests.post(
            f"{MOCK_SERVER_URL}/auth/login",
            json={"matricule": matricule, "password": password},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.token = data["access_token"]
            st.session_state.matricule = matricule
            st.session_state.user_name = f"{data['user']['prenom']} {data['user']['nom']}"
            st.session_state.user_role = data["user"]["role"]
            st.session_state.messages = []
            st.session_state.timestamps = []
            st.session_state.response_times = []
            st.session_state.tool_calls_count = 0
            st.session_state.turn_count = 0
            st.session_state.thread_id = f"{matricule}-{uuid.uuid4().hex[:8]}"
            try:
                st.session_state.agent = get_cached_agent()
            except Exception as e:
                print(f"[ERROR] Failed to build agent during login: {e}", flush=True)
                st.session_state.agent = None
            st.rerun()
        else:
            st.sidebar.error(f"Login failed (HTTP {resp.status_code})")
    except requests.ConnectionError:
        st.sidebar.error("Server unreachable. Run: python main.py")


def do_logout():
    for k in defaults:
        st.session_state[k] = defaults[k] if not isinstance(defaults[k], list) else []
    st.rerun()


def clear_conversation():
    st.session_state.messages = []
    st.session_state.timestamps = []
    st.session_state.response_times = []
    st.session_state.tool_calls_count = 0
    st.session_state.turn_count = 0
    st.session_state.thread_id = f"{st.session_state.matricule}-{uuid.uuid4().hex[:8]}"
    st.rerun()


def export_conversation() -> str:
    export = []
    for i, msg in enumerate(st.session_state.messages):
        if isinstance(msg, SystemMessage):
            continue
        ts = st.session_state.timestamps[i] if i < len(st.session_state.timestamps) else ""
        entry = {"role": msg.type, "content": msg.content, "timestamp": ts}
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            entry["tool_calls"] = [{"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls]
        export.append(entry)
    return json.dumps(export, indent=2, ensure_ascii=False)


def _extract_text(content) -> str:
    """Normalize LLM content to plain text.

    Gemini 2.5 Flash returns content as a list of dicts:
      [{'type': 'text', 'text': '...'}, ...]
    Ollama/OpenAI returns a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


# ── Streaming Engine ──────────────────────────────────────────

_TOOL_LABELS = {
    "search_knowledge_base": "\U0001f4da Recherche dans la base de connaissances\u2026",
    "get_personal_dossiers": "\U0001f50d R\u00e9cup\u00e9ration de vos dossiers\u2026",
    "escalate_to_human": "\U0001f464 Transfert vers un agent humain\u2026",
    "analyze_medical_receipt": "\U0001f9fe Analyse de la facture m\u00e9dicale\u2026",
}


def _stream_events(agent, state: dict, config: dict):
    """Sync generator bridging async LangGraph astream_events to Streamlit.

    Yields dicts with keys: event, name, data.
    Uses a background thread + queue so Streamlit's main thread
    can iterate synchronously while the async loop runs.
    """
    q: queue_module.Queue = queue_module.Queue()

    def _worker():
        loop = asyncio.new_event_loop()
        async def _run():
            async for ev in agent.astream_events(
                state, config=config, version="v2"
            ):
                q.put(ev)
            q.put(None)  # sentinel
        try:
            loop.run_until_complete(_run())
        except Exception as exc:
            q.put({"event": "error", "data": str(exc)})
            q.put(None)
        finally:
            loop.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while True:
        try:
            ev = q.get(timeout=120)
        except queue_module.Empty:
            yield {"event": "error", "data": "Timeout : l\u2019IA n\u2019a pas r\u00e9pondu dans les 2 minutes."}
            break
        if ev is None:
            break
        yield ev

    thread.join(timeout=5)


def _enqueue_message(msg):
    """Add a user message to session state and trigger streaming."""
    st.session_state.messages.append(msg)
    st.session_state.timestamps.append(datetime.now().strftime("%H:%M:%S"))
    st.session_state.streaming = True


# ── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("#### I-Sante")
    st.caption("AI Insurance Assistant")
    st.divider()

    if st.session_state.token:
        st.markdown(f"**{st.session_state.user_name}**")
        st.caption(f"{st.session_state.user_role}  ·  ID {st.session_state.matricule}")

        mode = "Local / " + OLLAMA_MODEL if USE_LOCAL_LLM else "Cloud / Gemini"
        st.caption(f"LLM: {mode}")

        st.divider()

        if st.button("Clear Chat", use_container_width=True):
            clear_conversation()
        if st.button("Logout", use_container_width=True):
            do_logout()

        if st.session_state.messages:
            st.divider()
            st.download_button(
                label="Export Transcript",
                data=export_conversation(),
                file_name=f"isante_{st.session_state.matricule}_{datetime.now().strftime('%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )

        st.divider()
        st.markdown("##### Stats")
        c1, c2 = st.columns(2)
        c1.metric("Turns", st.session_state.turn_count)
        c2.metric("Tools", st.session_state.tool_calls_count)
        if st.session_state.response_times:
            avg = sum(st.session_state.response_times) / len(st.session_state.response_times)
            st.caption(f"Avg response: {avg:.1f}s")

    else:
        st.markdown("##### Connect")
        st.caption("Select a test profile:")

        if st.button("Nadia Mansour  —  Adherente", use_container_width=True, key="login_nadia"):
            do_login("12345", "pass")
        if st.button("Dr. Amine Zaid  —  Prestataire", use_container_width=True, key="login_amine"):
            do_login("99999", "med")

    st.divider()
    st.caption("I-Way Solutions · v1.0")


# ── Header ────────────────────────────────────────────────────

if st.session_state.token:
    mode_label = "Local / " + OLLAMA_MODEL if USE_LOCAL_LLM else "Cloud / Gemini 2.5 Flash"
    badge_cls = "badge-local" if USE_LOCAL_LLM else "badge-cloud"
    st.markdown(f"""
    <div class="main-header">
        <div>
            <div class="title">I-Sante Virtual Assistant</div>
            <div class="subtitle">Healthcare Insurance AI — I-Way Solutions</div>
        </div>
        <div style="display: flex; gap: 0.6rem; align-items: center;">
            <span class="badge-user">{st.session_state.user_name}</span>
            <span class="header-badge {badge_cls}">{mode_label}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="main-header">
        <div>
            <div class="title">I-Sante Virtual Assistant</div>
            <div class="subtitle">Healthcare Insurance AI — I-Way Solutions</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Not Logged In ─────────────────────────────────────────────

if not st.session_state.token:
    st.markdown("""
    <div class="welcome-card">
        <h3>Welcome to I-Sante</h3>
        <p>Connect via the sidebar to start a conversation with the AI assistant.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("**Available test profiles:**")
        st.markdown("""
        | Profile | ID | Password | Role |
        |---|---|---|---|
        | Nadia Mansour | `12345` | `pass` | Adherente |
        | Dr. Amine Zaid | `99999` | `med` | Prestataire |
        """)
        st.info("Make sure the mock server is running: `python main.py`")

    st.stop()


# ── Metrics Bar ───────────────────────────────────────────────

if st.session_state.turn_count > 0:
    avg_time = (
        f"{sum(st.session_state.response_times) / len(st.session_state.response_times):.1f}s"
        if st.session_state.response_times else "—"
    )
    st.markdown(f"""
    <div class="metrics-strip">
        <div class="metric-pill">
            <div class="metric-icon icon-blue">T</div>
            <div class="metric-data">
                <div class="metric-value">{st.session_state.turn_count}</div>
                <div class="metric-label">Turns</div>
            </div>
        </div>
        <div class="metric-pill">
            <div class="metric-icon icon-green">F</div>
            <div class="metric-data">
                <div class="metric-value">{st.session_state.tool_calls_count}</div>
                <div class="metric-label">Tool Calls</div>
            </div>
        </div>
        <div class="metric-pill">
            <div class="metric-icon icon-purple">R</div>
            <div class="metric-data">
                <div class="metric-value">{avg_time}</div>
                <div class="metric-label">Avg Response</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Quick Actions (only on fresh conversation) ────────────────

QUICK_QUESTIONS = [
    "Quels sont mes dossiers en cours ?",
    "Quel est le plafond dentaire ?",
    "Quelle est la prime de naissance ?",
    "Quel est le delai de remboursement ?",
    "Je veux parler a un agent humain",
]

if st.session_state.turn_count == 0 and not st.session_state.streaming:
    st.markdown('<div class="quick-label">Quick Start \u2014 click a question</div>', unsafe_allow_html=True)
    row1 = st.columns(3)
    row2 = st.columns(3)
    all_cols = row1 + row2
    for i, q in enumerate(QUICK_QUESTIONS):
        with all_cols[i]:
            if st.button(q, key=f"qa_{i}", use_container_width=True):
                _enqueue_message(HumanMessage(content=q))
                st.rerun()


# ── Display Chat History ──────────────────────────────────────

for idx, msg in enumerate(st.session_state.messages):
    if isinstance(msg, SystemMessage):
        continue

    ts = st.session_state.timestamps[idx] if idx < len(st.session_state.timestamps) else ""

    if isinstance(msg, ToolMessage):
        with st.chat_message("assistant"):
            st.markdown(
                f'<div class="tool-trace-block">'
                f'<span class="tool-label">[{msg.name}]</span> '
                f'{msg.content[:400]}{"..." if len(msg.content) > 400 else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
        continue

    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            # Handle multi-modal messages (text + image)
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        st.markdown(block["text"])
                    elif isinstance(block, dict) and block.get("type") == "image_url":
                        st.image(block["image_url"]["url"], caption="Facture m\u00e9dicale", width=300)
            else:
                st.markdown(msg.content)
            if ts:
                st.markdown(f'<div class="ts">{ts}</div>', unsafe_allow_html=True)

    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, "tool_calls") and msg.tool_calls and not msg.content:
                tools_list = ", ".join(tc["name"] for tc in msg.tool_calls)
                st.caption(f"Calling: {tools_list}")
            elif msg.content:
                display_text = _extract_text(msg.content)
                if display_text:
                    st.markdown(display_text)
                if ts:
                    st.markdown(f'<div class="ts">{ts}</div>', unsafe_allow_html=True)


# ── Streaming Response Block ───────────────────────────────

if st.session_state.streaming and st.session_state.messages:
    last_msg = st.session_state.messages[-1]
    if isinstance(last_msg, HumanMessage):
        # Lazy-init agent if it wasn't created during login
        if st.session_state.agent is None:
            try:
                with st.spinner("Loading AI model (first time may take a minute)..."):
                    st.session_state.agent = get_cached_agent()
            except Exception as e:
                st.error(f"Failed to initialize AI agent: {e}")
                print(f"[ERROR] Agent init failed: {e}", flush=True)
                import traceback; traceback.print_exc()
                st.session_state.streaming = False
                st.stop()

        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        state = {
            "messages": [last_msg],
            "matricule": st.session_state.matricule,
            "token": st.session_state.token,
        }

        t_start = time.time()
        accumulated = ""
        had_error = False

        with st.chat_message("assistant"):
            tool_status = st.empty()
            response_area = st.empty()

            try:
                for ev in _stream_events(st.session_state.agent, state, config):
                    kind = ev.get("event", "")

                    if kind == "on_tool_start":
                        name = ev.get("name", "")
                        label = _TOOL_LABELS.get(name, f"\U0001f527 {name}\u2026")
                        tool_status.info(label)

                    elif kind == "on_tool_end":
                        tool_status.empty()

                    elif kind == "on_chat_model_stream":
                        chunk = ev.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            text = _extract_text(chunk.content)
                            if text:
                                accumulated += text
                                response_area.markdown(accumulated + " \u258c")

                    elif kind == "error":
                        err = ev.get("data", "Erreur inconnue")
                        print(f"[ERROR] Streaming error: {err}", flush=True)
                        if "500" in str(err):
                            response_area.error(
                                "Erreur 500 : V\u00e9rifiez le mod\u00e8le Ollama "
                                "(`ollama list`) et la VRAM disponible."
                            )
                        else:
                            response_area.error(f"Erreur: {err}")
                        had_error = True

            except Exception as exc:
                print(f"[ERROR] Exception during streaming: {type(exc).__name__}: {exc}", flush=True)
                import traceback; traceback.print_exc()
                response_area.error(f"Erreur: {exc}")
                had_error = True

            # Finalize the streamed response
            tool_status.empty()
            if accumulated:
                response_area.markdown(accumulated)

        elapsed = time.time() - t_start

        # Read final state from the checkpointer
        if not had_error:
            state_saved = False
            try:
                final_state = st.session_state.agent.get_state(config)
                result_messages = list(final_state.values["messages"])

                # Fallback: if streaming didn't capture any tokens,
                # extract the final AI response from the checkpointer
                if not accumulated and result_messages:
                    for m in reversed(result_messages):
                        if isinstance(m, AIMessage) and m.content:
                            fallback_text = _extract_text(m.content)
                            if fallback_text:
                                response_area.markdown(fallback_text)
                            break

                new_messages = result_messages[len(st.session_state.messages):]
                turn_tools = sum(
                    len(m.tool_calls)
                    for m in new_messages
                    if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls
                )

                st.session_state.messages = result_messages
                while len(st.session_state.timestamps) < len(result_messages):
                    st.session_state.timestamps.append(datetime.now().strftime("%H:%M:%S"))

                st.session_state.turn_count += 1
                st.session_state.tool_calls_count += turn_tools
                st.session_state.response_times.append(elapsed)
                state_saved = True
            except Exception as exc:
                print(f"[WARN] get_state() failed: {exc}", flush=True)

            # Fallback: if checkpointer didn't save state, manually
            # append the AI response so it persists across reruns
            if not state_saved and accumulated:
                st.session_state.messages.append(
                    AIMessage(content=accumulated)
                )
                st.session_state.timestamps.append(
                    datetime.now().strftime("%H:%M:%S")
                )
                st.session_state.turn_count += 1
                st.session_state.response_times.append(elapsed)

        st.session_state.streaming = False
        st.rerun()


# ── Chat Input + Image Upload ─────────────────────────────────

def _on_file_upload():
    """Callback: auto-enqueue the uploaded receipt for analysis."""
    f = st.session_state.get("receipt_upload")
    if f is not None:
        b64 = base64.b64encode(f.getvalue()).decode("utf-8")
        mime = "image/png" if f.name.lower().endswith(".png") else "image/jpeg"
        img_msg = HumanMessage(content=[
            {"type": "text", "text": "Analyse cette facture m\u00e9dicale et calcule mon remboursement."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])
        _enqueue_message(img_msg)


col_upload, col_input = st.columns([1, 3])
with col_upload:
    st.file_uploader(
        "\U0001f4f7 Joindre une facture",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed",
        key="receipt_upload",
        on_change=_on_file_upload,
    )

if user_input := st.chat_input("Posez votre question..."):
    _enqueue_message(HumanMessage(content=user_input))
    st.rerun()
