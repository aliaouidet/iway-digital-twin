"""
WebSocket Connection Manager — Role-aware broadcasts to connected clients.

Each connection is tagged with its JWT-verified role on connect.
The broadcast() method supports target_roles filtering so that
sensitive events (escalations, pipeline traces) are only sent to
authorized Agent/Admin connections — never to regular Adherent clients.
"""

import logging
from typing import Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("I-Way-Twin")


class ConnectionManager:
    """Manages active WebSocket connections with role-based broadcasting."""

    def __init__(self):
        # Each entry: {"ws": WebSocket, "role": str, "matricule": str}
        self.active_connections: list[dict] = []

    async def connect(self, websocket: WebSocket, role: str = "Adherent", matricule: str = ""):
        """Accept and register a WebSocket with its verified JWT role."""
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

        Automatically removes dead connections on send failure
        to prevent memory leaks from accumulated stale references.
        """
        dead_connections = []
        sent_count = 0

        for conn in list(self.active_connections):
            # Role filter: skip connections that don't match target roles
            if target_roles and conn["role"] not in target_roles:
                continue

            try:
                await conn["ws"].send_json(message)
                sent_count += 1
            except Exception:
                dead_connections.append(conn)

        # Clean up dead connections after iteration
        if dead_connections:
            for dead in dead_connections:
                if dead in self.active_connections:
                    self.active_connections.remove(dead)
            logger.info(
                f"🧹 Removed {len(dead_connections)} dead WebSocket connection(s). "
                f"Active: {len(self.active_connections)}"
            )

        if target_roles:
            logger.debug(
                f"Broadcast to roles {target_roles}: {sent_count} recipient(s)"
            )
