"""
WebSocket Connection Manager — Role-aware broadcasts to connected clients.

Each connection is tagged with its JWT-verified role on connect.
The broadcast() method supports target_roles filtering so that
sensitive events (escalations, pipeline traces) are only sent to
authorized Agent/Admin connections — never to regular Adherent clients.
"""

import asyncio
import logging
from typing import Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("I-Way-Twin")

# A single slow/half-dead consumer must not stall escalation notifications for
# everyone — each send gets its own deadline.
_SEND_TIMEOUT_SECONDS = 2.0


class ConnectionManager:
    """Manages active WebSocket connections with role-based broadcasting."""

    def __init__(self):
        # Each entry: {"ws": WebSocket, "role": str, "matricule": str}
        self.active_connections: list[dict] = []

    async def connect(self, websocket: WebSocket, role: str = "Adherent", matricule: str = "",
                      accepted: bool = False):
        """Register a WebSocket with its verified JWT role.

        `accepted=True` means the endpoint already accepted the socket (the
        first-frame auth handshake accepts before validating) — don't re-accept.
        """
        if not accepted:
            await websocket.accept()
        self.active_connections.append({
            "ws": websocket,
            "role": role,
            "matricule": matricule,
        })
        logger.info(
            f"WebSocket connected (role={role}, matricule={matricule}). "
            f"Active: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket from the active pool."""
        self.active_connections = [
            conn for conn in self.active_connections
            if conn["ws"] is not websocket
        ]
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(
        self,
        message: dict,
        target_roles: Optional[Set[str]] = None,
    ):
        """Broadcast a message to connected WebSockets, optionally filtered by role.

        Args:
            message: JSON-serializable dict to send.
            target_roles: If set, only connections whose role is in this set
                          will receive the message. If None, all connections
                          receive it (backward-compatible default).

        Sends run CONCURRENTLY with a per-send timeout — a single slow consumer
        no longer head-of-line-blocks every other recipient. Dead connections
        are removed on failure to prevent stale-reference leaks.
        """
        targets = [
            conn for conn in list(self.active_connections)
            if not target_roles or conn["role"] in target_roles
        ]
        if not targets:
            return

        async def _send(conn):
            await asyncio.wait_for(conn["ws"].send_json(message), timeout=_SEND_TIMEOUT_SECONDS)

        results = await asyncio.gather(*(_send(c) for c in targets), return_exceptions=True)

        dead_connections = [c for c, r in zip(targets, results) if isinstance(r, BaseException)]
        sent_count = len(targets) - len(dead_connections)

        if dead_connections:
            for dead in dead_connections:
                if dead in self.active_connections:
                    self.active_connections.remove(dead)
            logger.info(
                f"🧹 Removed {len(dead_connections)} dead/stalled WebSocket connection(s). "
                f"Active: {len(self.active_connections)}"
            )

        if target_roles:
            logger.debug(
                f"Broadcast to roles {target_roles}: {sent_count} recipient(s)"
            )
