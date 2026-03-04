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
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Theme & Styling ───────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp {
        max-width: 860px;
        margin: 0 auto;
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stSidebarContent"] {
        padding-top: 1rem;
    }

    /* Header bar */
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.6rem 1rem;
        background: linear-gradient(135deg, #1a5276, #2e86c1);
        border-radius: 10px;
        margin-bottom: 1rem;
        color: white;
    }
    .app-header h2 {
        margin: 0;
        font-size: 1.3rem;
        font-weight: 600;
    }
    .app-header .subtitle {
        font-size: 0.78rem;
        opacity: 0.85;
    }

    /* Status badges */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .badge-cloud { background: #d4efdf; color: #1e8449; }
    .badge-local { background: #fdebd0; color: #b9770e; }
    .badge-online { background: #d5f5e3; color: #196f3d; }

    /* Metrics row */
    .metrics-row {
        display: flex;
        gap: 0.7rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        flex: 1;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 0.6rem 0.8rem;
        text-align: center;
    }
    .metric-card .label {
        font-size: 0.68rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-card .value {
        font-size: 1.15rem;
        font-weight: 700;
        color: #2c3e50;
    }

    /* Quick actions */
    .quick-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-bottom: 1rem;
    }

    /* Tool trace */
    .tool-trace {
        background: #f0f4f8;
        border-left: 3px solid #2e86c1;
        padding: 0.5rem 0.8rem;
        margin: 0.3rem 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.82rem;
    }
    .tool-trace .tool-name {
        font-weight: 600;
        color: #2e86c1;
    }

    /* Timestamp on messages */
    .msg-time {
        font-size: 0.65rem;
        color: #adb5bd;
        text-align: right;
        margin-top: 2px;
    }
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
    "response_times": [],       # track latency
    "tool_calls_count": 0,      # total tool invocations
    "turn_count": 0,            # conversation turns
    "timestamps": [],           # per-message timestamps
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Login / Logout Helpers ────────────────────────────────────

def do_login(matricule: str, password: str):
    """Authenticate against the Mock Server and build the agent graph."""
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
            st.session_state.agent = build_agent_graph()
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
    """Export chat history as JSON."""
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


# ── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Connexion")

    if st.session_state.token:
        st.markdown(f"**{st.session_state.user_name}**")
        st.caption(f"Role: {st.session_state.user_role}  |  ID: {st.session_state.matricule}")

        # Connection info
        mode = "Local / " + OLLAMA_MODEL if USE_LOCAL_LLM else "Cloud / Gemini 2.5 Flash"
        badge = "badge-local" if USE_LOCAL_LLM else "badge-cloud"
        st.markdown(f'<span class="badge {badge}">LLM: {mode}</span>', unsafe_allow_html=True)

        st.divider()

        # Session controls
        st.markdown("##### Session")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear Chat", use_container_width=True):
                clear_conversation()
        with col2:
            if st.button("Logout", use_container_width=True):
                do_logout()

        # Export
        if st.session_state.messages:
            export_data = export_conversation()
            st.download_button(
                label="Export Transcript",
                data=export_data,
                file_name=f"isante_chat_{st.session_state.matricule}_{datetime.now().strftime('%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )

        st.divider()

        # Session stats
        st.markdown("##### Statistics")
        st.caption(f"Turns: {st.session_state.turn_count}")
        st.caption(f"Tool calls: {st.session_state.tool_calls_count}")
        if st.session_state.response_times:
            avg = sum(st.session_state.response_times) / len(st.session_state.response_times)
            st.caption(f"Avg response: {avg:.1f}s")

    else:
        st.info("Select a test profile to start:")

        if st.button("Nadia Mansour  (Adherente)", use_container_width=True):
            do_login("12345", "pass")
        if st.button("Dr. Amine Zaid  (Prestataire)", use_container_width=True):
            do_login("99999", "med")

    st.divider()
    st.caption("I-Way Solutions  |  I-Sante v1.0")


# ── Header ────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
    <div>
        <h2>I-Sante Virtual Assistant</h2>
        <div class="subtitle">Healthcare Insurance AI — I-Way Solutions</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Not Logged In ─────────────────────────────────────────────

if not st.session_state.token:
    st.markdown("""
    Connect via the sidebar to start a conversation with the AI assistant.

    **Available test profiles:**

    | Profile | ID | Password | Role |
    |---|---|---|---|
    | Nadia Mansour | `12345` | `pass` | Adherente |
    | Dr. Amine Zaid | `99999` | `med` | Prestataire |

    **Prerequisites:** Mock server must be running (`python main.py`)
    """)
    st.stop()


# ── Metrics Bar ───────────────────────────────────────────────

if st.session_state.turn_count > 0:
    avg_time = (
        f"{sum(st.session_state.response_times) / len(st.session_state.response_times):.1f}s"
        if st.session_state.response_times else "—"
    )
    st.markdown(f"""
    <div class="metrics-row">
        <div class="metric-card">
            <div class="label">Turns</div>
            <div class="value">{st.session_state.turn_count}</div>
        </div>
        <div class="metric-card">
            <div class="label">Tool Calls</div>
            <div class="value">{st.session_state.tool_calls_count}</div>
        </div>
        <div class="metric-card">
            <div class="label">Avg Response</div>
            <div class="value">{avg_time}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Quick Action Buttons ──────────────────────────────────────

if st.session_state.turn_count == 0:
    st.markdown("**Quick start — click a question:**")
    quick_questions = [
        "Quels sont mes dossiers en cours ?",
        "Quel est le plafond dentaire ?",
        "Quelle est la prime de naissance ?",
        "Quel est le delai de remboursement ?",
        "Je veux parler a un agent humain",
    ]

    cols = st.columns(len(quick_questions))
    for i, q in enumerate(quick_questions):
        with cols[i]:
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                st.session_state._pending_quick = q
                st.rerun()


# ── Display Chat History ──────────────────────────────────────

for idx, msg in enumerate(st.session_state.messages):
    if isinstance(msg, SystemMessage):
        continue

    ts = st.session_state.timestamps[idx] if idx < len(st.session_state.timestamps) else ""

    if isinstance(msg, ToolMessage):
        # Show tool results inline as a styled trace block
        with st.chat_message("assistant"):
            st.markdown(
                f'<div class="tool-trace">'
                f'<span class="tool-name">[{msg.name}]</span> '
                f'{msg.content[:300]}{"..." if len(msg.content) > 300 else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
        continue

    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
            if ts:
                st.markdown(f'<div class="msg-time">{ts}</div>', unsafe_allow_html=True)

    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, "tool_calls") and msg.tool_calls and not msg.content:
                tools_list = ", ".join(tc["name"] for tc in msg.tool_calls)
                st.caption(f"Calling tools: {tools_list}")
            elif msg.content:
                st.markdown(msg.content)
                if ts:
                    st.markdown(f'<div class="msg-time">{ts}</div>', unsafe_allow_html=True)


# ── Process Pending Quick Action ──────────────────────────────

pending = st.session_state.pop("_pending_quick", None)


# ── Chat Input ────────────────────────────────────────────────

user_input = pending or st.chat_input("Posez votre question...")

if user_input:
    now_str = datetime.now().strftime("%H:%M:%S")

    user_msg = HumanMessage(content=user_input)
    st.session_state.messages.append(user_msg)
    st.session_state.timestamps.append(now_str)

    with st.chat_message("user"):
        st.markdown(user_input)
        st.markdown(f'<div class="msg-time">{now_str}</div>', unsafe_allow_html=True)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        status_placeholder.caption("Processing...")

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

            # Count tool calls in this turn
            turn_tools = 0
            tool_details = []
            for m in new_messages:
                if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        turn_tools += 1
                        tool_details.append(("call", tc["name"], json.dumps(tc["args"], ensure_ascii=False)))
                elif isinstance(m, ToolMessage):
                    tool_details.append(("result", m.name, m.content))

            status_placeholder.empty()

            # Show tool trace
            if tool_details:
                with st.expander(f"Tool trace  ({turn_tools} call{'s' if turn_tools != 1 else ''})", expanded=False):
                    for kind, name, content in tool_details:
                        if kind == "call":
                            st.markdown(f"**{name}**")
                            st.code(content, language="json")
                        else:
                            st.markdown(f"**{name}** returned:")
                            st.code(content[:500], language="text")

            # Show final response
            final_msg = result_messages[-1] if result_messages else None
            if final_msg and isinstance(final_msg, AIMessage) and final_msg.content:
                st.markdown(final_msg.content)
                resp_ts = datetime.now().strftime("%H:%M:%S")
                st.markdown(f'<div class="msg-time">{resp_ts}  |  {elapsed:.1f}s</div>', unsafe_allow_html=True)
            else:
                st.warning("The assistant could not generate a response.")

            # Update state
            st.session_state.messages = result_messages
            # Pad timestamps for new messages
            while len(st.session_state.timestamps) < len(result_messages):
                st.session_state.timestamps.append(datetime.now().strftime("%H:%M:%S"))

            st.session_state.turn_count += 1
            st.session_state.tool_calls_count += turn_tools
            st.session_state.response_times.append(elapsed)

        except Exception as e:
            status_placeholder.empty()
            st.error(f"Error: {str(e)}")
