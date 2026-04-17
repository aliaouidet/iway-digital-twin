"""
Test Suite: WebSocket Chat Flow (Agent Integration)

Tests the WebSocket-based chat including:
- Connection & history
- AI response streaming (tokens)
- Manual handoff
- Ping/pong keepalive

Run:
  cd /home/azmi/Desktop/pfe/iway-digital-twin
  source .venv/bin/activate
  python -m pytest tests/test_websocket.py -v

Requires: Backend running on localhost:8000
"""

import json
import asyncio
import httpx
import pytest

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


def login(matricule: str, password: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"matricule": matricule, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def create_session(token: str) -> str:
    r = httpx.post(f"{BASE}/sessions/create", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()["session_id"]


class TestWebSocket:
    """Test WebSocket chat flows."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("12345", "pass")
        self.session_id = create_session(self.token)

    @pytest.mark.asyncio
    async def test_user_connect(self):
        """Test WebSocket connection and user_connect handshake."""
        import websockets

        uri = f"{WS_BASE}/ws/chat/{self.session_id}?token={self.token}"
        async with websockets.connect(uri) as ws:
            # Send user_connect
            await ws.send(json.dumps({"type": "user_connect"}))
            # Should receive 'connected' response
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert resp["type"] == "connected"
            assert resp["role"] == "user"

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        """Test keepalive ping/pong."""
        import websockets

        uri = f"{WS_BASE}/ws/chat/{self.session_id}?token={self.token}"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "user_connect"}))
            await asyncio.wait_for(ws.recv(), timeout=5)  # connected
            await asyncio.wait_for(ws.recv(), timeout=5)  # history

            await ws.send(json.dumps({"type": "PING"}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert resp["type"] == "PONG"

    @pytest.mark.asyncio
    async def test_user_message_gets_response(self):
        """Test sending a message and receiving AI response tokens."""
        import websockets

        uri = f"{WS_BASE}/ws/chat/{self.session_id}?token={self.token}"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "user_connect"}))
            await asyncio.wait_for(ws.recv(), timeout=5)  # connected
            await asyncio.wait_for(ws.recv(), timeout=5)  # history

            # Send message
            await ws.send(json.dumps({"type": "user_message", "content": "Bonjour"}))

            # Collect responses (thinking, ai_token, ai_done)
            responses = []
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    msg = json.loads(raw)
                    responses.append(msg)
                    if msg["type"] == "ai_done" or msg["type"] == "handoff_started":
                        break
            except asyncio.TimeoutError:
                pass

            # Should have at least thinking + some response
            types = [r["type"] for r in responses]
            assert "thinking" in types, f"Expected 'thinking' in {types}"
            # Should end with ai_done or handoff
            assert types[-1] in ("ai_done", "handoff_started"), f"Unexpected final type: {types[-1]}"

    @pytest.mark.asyncio
    async def test_manual_handoff(self):
        """Test manual escalation request."""
        import websockets

        uri = f"{WS_BASE}/ws/chat/{self.session_id}?token={self.token}"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "user_connect"}))
            await asyncio.wait_for(ws.recv(), timeout=5)
            await asyncio.wait_for(ws.recv(), timeout=5)

            await ws.send(json.dumps({"type": "manual_handoff_request"}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert resp["type"] == "handoff_started"
            assert "reason" in resp

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self):
        """Test that empty messages are ignored."""
        import websockets

        uri = f"{WS_BASE}/ws/chat/{self.session_id}?token={self.token}"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "user_connect"}))
            await asyncio.wait_for(ws.recv(), timeout=5)
            await asyncio.wait_for(ws.recv(), timeout=5)

            # Send empty message
            await ws.send(json.dumps({"type": "user_message", "content": ""}))
            # Send ping to check we're still connected
            await ws.send(json.dumps({"type": "PING"}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert resp["type"] == "PONG"
