"""
WebSocket Connection Manager — Broadcasts events to connected clients.

NOTE (Production TODO): Currently broadcasts all events to all connections.
In production, add role-based filtering so that only agents/admins
receive escalation events containing user PII.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger("I-Way-Twin")


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSockets.

        Automatically removes dead connections on send failure
        to prevent memory leaks from accumulated stale references.
        """
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        # Clean up dead connections after iteration
        for dead in dead_connections:
            if dead in self.active_connections:
                self.active_connections.remove(dead)
        if dead_connections:
            logger.info(
                f"🧹 Removed {len(dead_connections)} dead WebSocket connection(s). "
                f"Active: {len(self.active_connections)}"
            )
