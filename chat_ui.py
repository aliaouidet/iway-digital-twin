"""
chat_ui.py — Streamlit Chat UI for the I-Sante Virtual Assistant.

Run:   streamlit run chat_ui.py
Requires: Mock Server running on :8000  (python main.py)
"""

import os
import time
import json
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
    rag_engine.get_engine()  # Pre-load sentence-transformers model
    return build_agent_graph()


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
            st.session_state.agent = get_cached_agent()
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


def send_message(text: str):
    """Process a user message through the LangGraph agent."""
    now_str = datetime.now().strftime("%H:%M:%S")
    user_msg = HumanMessage(content=text)
    st.session_state.messages.append(user_msg)
    st.session_state.timestamps.append(now_str)

    t_start = time.time()

    try:
        result = st.session_state.agent.invoke({
            "messages": st.session_state.messages,
            "matricule": st.session_state.matricule,
            "token": st.session_state.token,
        })

        elapsed = time.time() - t_start
        result_messages = result.get("messages", [])
        new_messages = result_messages[len(st.session_state.messages):]

        turn_tools = 0
        for m in new_messages:
            if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                turn_tools += len(m.tool_calls)

        st.session_state.messages = result_messages
        while len(st.session_state.timestamps) < len(result_messages):
            st.session_state.timestamps.append(datetime.now().strftime("%H:%M:%S"))

        st.session_state.turn_count += 1
        st.session_state.tool_calls_count += turn_tools
        st.session_state.response_times.append(elapsed)

    except Exception as e:
        st.session_state.messages.append(
            AIMessage(content=f"Error: {str(e)}")
        )
        st.session_state.timestamps.append(datetime.now().strftime("%H:%M:%S"))


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

if st.session_state.turn_count == 0:
    st.markdown('<div class="quick-label">Quick Start — click a question</div>', unsafe_allow_html=True)
    row1 = st.columns(3)
    row2 = st.columns(3)
    all_cols = row1 + row2
    for i, q in enumerate(QUICK_QUESTIONS):
        with all_cols[i]:
            if st.button(q, key=f"qa_{i}", use_container_width=True):
                send_message(q)
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
            st.markdown(msg.content)
            if ts:
                st.markdown(f'<div class="ts">{ts}</div>', unsafe_allow_html=True)

    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, "tool_calls") and msg.tool_calls and not msg.content:
                tools_list = ", ".join(tc["name"] for tc in msg.tool_calls)
                st.caption(f"Calling: {tools_list}")
            elif msg.content:
                st.markdown(msg.content)
                if ts:
                    st.markdown(f'<div class="ts">{ts}</div>', unsafe_allow_html=True)


# ── Chat Input ────────────────────────────────────────────────

if user_input := st.chat_input("Posez votre question..."):
    send_message(user_input)
    st.rerun()
