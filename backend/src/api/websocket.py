"""
IBVAP — WebSocket Manager
Real-time alert broadcasting with per-connection identity.
"""

import asyncio
import json
import time

from fastapi import WebSocket
from loguru import logger

from src.api import auth as _auth


async def authenticate_ws(websocket: WebSocket) -> dict | None:
    """Verify the socket's bearer token, close it on failure.

    Accepts either:
      - `Sec-WebSocket-Protocol: bearer, <jwt>` (preferred — token stays out of URLs/logs)
      - `?token=<jwt>` query param (legacy fallback)

    Returns the decoded token payload on success (and completes the handshake),
    or None after closing the socket.
    """
    token: str | None = None
    subprotocol: str | None = None

    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    if len(offered) >= 2 and offered[0] == "bearer":
        token, subprotocol = offered[1], "bearer"
    if token is None:
        token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001, reason="Missing auth token")
        return None
    try:
        payload = _auth._verify_token(token)
        _auth._deny_if_revoked(token)
        profile = _auth.resolve_profile(payload["sub"])
    except Exception:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return None

    await websocket.accept(subprotocol=subprotocol)
    return {**payload, "token": token, "user_id": payload["sub"],
            "app_role": profile["role"], "allowed_areas": profile["allowed_areas"]}


class WebSocketManager:
    """Manages WebSocket connections for real-time alert broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._identities: dict = {}  # id(websocket) -> token payload
        self._lock = asyncio.Lock()
        self._loop = None

    async def connect(self, websocket: WebSocket, identity: dict | None = None):
        # NOTE: the socket is already accepted by authenticate_ws
        async with self._lock:
            self.active_connections.append(websocket)
            self._identities[id(websocket)] = identity or {}
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            self._identities.pop(id(websocket), None)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    def token_expired(self, websocket: WebSocket) -> bool:
        exp = (self._identities.get(id(websocket)) or {}).get("exp")
        return bool(exp) and time.time() >= exp

    async def refresh_identity(self, websocket: WebSocket) -> dict | None:
        try:
            identity = _auth.refresh_media_identity(self._identities[id(websocket)])
            self._identities[id(websocket)] = identity
            return identity
        except Exception:
            await websocket.close(code=4003, reason="Authorization expired or unavailable")
            await self.disconnect(websocket)
            return None

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        data = json.dumps(message)
        disconnected = []

        for connection in list(self.active_connections):
            identity = await self.refresh_identity(connection)
            if identity is None:
                continue
            camera_id = message.get("data", {}).get("camera_id")
            if not camera_id or not _auth.can_access_camera(identity, camera_id):
                continue
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    def attach_loop(self, loop):
        """Capture the running event loop so non-async threads can schedule broadcasts."""
        self._loop = loop

    def broadcast_sync(self, message: dict):
        """Schedule a broadcast from a worker thread (e.g. a camera pipeline)."""
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.warning("broadcast_sync: no running loop attached; alert not pushed to WS clients")
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as e:
            logger.error(f"broadcast_sync failed: {e}")

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# Global WebSocket manager
ws_manager = WebSocketManager()
