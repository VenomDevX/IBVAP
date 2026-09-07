"""
IBVAP — WebSocket Manager
Real-time alert broadcasting via WebSocket connections.
"""

import json
import asyncio
from typing import List, Dict, Set
from fastapi import WebSocket
from loguru import logger


class WebSocketManager:
    """Manages WebSocket connections for real-time alert broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        data = json.dumps(message)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            async with self._lock:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    def broadcast_sync(self, message: dict):
        """Synchronous broadcast wrapper for use from non-async code."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.broadcast(message))
            else:
                loop.run_until_complete(self.broadcast(message))
        except RuntimeError:
            # No event loop available
            pass

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# Global WebSocket manager
ws_manager = WebSocketManager()
