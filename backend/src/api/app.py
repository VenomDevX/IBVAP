"""
IBVAP — FastAPI Application
AI Microservice: video analytics pipeline + REST API.
Frontend is served separately (Next.js static export behind nginx).
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.auth import require_auth
from src.api.middleware.input_validator import InputValidationMiddleware
from src.api.middleware.security import RequestLoggingMiddleware, SecurityHeadersMiddleware
from src.api.ratelimit import limiter
from src.api.routes import alerts, audit, cameras, events, reports, snapshots, statistics, stream, tracks, zones
from src.api.token_revocation import revoke_token
from src.api.websocket import authenticate_ws, ws_manager
from src.pipeline.pipeline import IBVAPPipeline

# Global pipeline reference
pipeline: IBVAPPipeline = None

_PLACEHOLDER_KEYS = {"", "change-me", "changeme", "test-hmac-key", "dev", "secret", "placeholder"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — start/stop pipeline."""
    global pipeline
    logger.info("Starting IBVAP application...")

    pipeline = IBVAPPipeline()
    pipeline.initialize()

    # Register WebSocket alert callback
    def alert_callback(alert_data: dict):
        ws_manager.broadcast_sync({"type": "alert", "data": alert_data})

    pipeline.alert_engine.register_callback(alert_callback)

    # Give the WS manager the running loop so camera worker threads can push alerts
    ws_manager.attach_loop(asyncio.get_running_loop())

    # Start camera pipelines
    pipeline.start_all()

    yield

    # Shutdown
    logger.info("Shutting down IBVAP...")
    if pipeline:
        pipeline.stop_all()


def _assert_production_config() -> None:
    """Fail fast rather than run degraded in production."""
    if os.getenv("SUPABASE_JWT_SECRET", "") == "":
        raise RuntimeError(
            "IBVAP_ENV=production but SUPABASE_JWT_SECRET is not set — every request "
            "would fail auth or fall back to a blocking network check."
        )
    if os.getenv("SUPABASE_SERVICE_KEY", "") == "":
        raise RuntimeError(
            "IBVAP_ENV=production but SUPABASE_SERVICE_KEY is not set — application "
            "roles can't be resolved and every user silently becomes 'operator'."
        )
    if os.getenv("EVIDENCE_HMAC_KEY", "").strip().lower() in _PLACEHOLDER_KEYS:
        raise RuntimeError(
            "IBVAP_ENV=production but EVIDENCE_HMAC_KEY is unset or a known placeholder — "
            "the evidence hash chain would be forgeable and unverifiable across restarts."
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Production mode disables interactive docs
    is_production = os.getenv("IBVAP_ENV", "development").lower() == "production"

    if is_production:
        _assert_production_config()

    app = FastAPI(
        title="IBVAP — Intelligent Border Video Analytics Platform",
        description="AI-Based Video Analytics for Border Surveillance",
        version="2.0.0",
        lifespan=lifespan,
        # Disable docs in production to prevent API exploration
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    # ======================== Security Middleware ========================
    # Order matters: first added = outermost layer (runs first on request)

    # 1. Trusted hosts — prevent host header injection attacks
    trusted_hosts = os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in trusted_hosts],
    )

    # 2. CORS — restrict to allowed frontend origins
    cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins if o.strip()],
        allow_credentials=False,  # pure bearer-token API, no cookies
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # 3. Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # 4. Security headers (XSS, clickjacking, MIME sniffing protection)
    app.add_middleware(SecurityHeadersMiddleware)

    # 5. Request logging with IP tracking and audit trail
    app.add_middleware(RequestLoggingMiddleware)

    # 6. Input validation (path traversal, injection, upload size)
    app.add_middleware(InputValidationMiddleware)

    # Snapshots dir (evidence images) — served via an authenticated route, NOT a static mount
    Path(os.getenv("IBVAP_SNAPSHOTS_DIR", "./outputs/snapshots")).mkdir(parents=True, exist_ok=True)

    # ======================== API Routes ========================
    app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
    app.include_router(events.router, prefix="/api/events", tags=["Events"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
    app.include_router(zones.router, prefix="/api/zones", tags=["Zones"])
    app.include_router(tracks.router, prefix="/api/tracks", tags=["Tracks"])
    app.include_router(statistics.router, prefix="/api/statistics", tags=["Statistics"])
    app.include_router(stream.router, prefix="/api/stream", tags=["Video Stream"])
    app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
    app.include_router(audit.router, prefix="/api/audit", tags=["Audit Logs"])
    app.include_router(snapshots.router, prefix="/snapshots", tags=["Snapshots"])

    # ======================== WebSocket ========================
    @app.websocket("/ws/alerts")
    async def websocket_alerts(websocket: WebSocket):
        """Live alert stream.

        Auth: prefer the `Sec-WebSocket-Protocol: bearer, <jwt>` handshake (the
        token never lands in a URL / access log); fall back to `?token=<jwt>`
        for older clients. The connection is dropped once the token's own `exp`
        passes so a revoked-by-expiry session can't linger on the socket.
        """
        identity = await authenticate_ws(websocket)
        if identity is None:
            return  # authenticate_ws already closed the socket with a reason

        await ws_manager.connect(websocket, identity)
        try:
            while True:
                # Inbound frames are not part of the protocol — read to detect
                # disconnects, cap the size, and otherwise ignore them.
                if await ws_manager.refresh_identity(websocket) is None:
                    break
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=5)
                except TimeoutError:
                    continue
                if len(msg) > 4096:
                    await websocket.close(code=1009, reason="Frame too large")
                    break
                if ws_manager.token_expired(websocket):
                    await websocket.close(code=4003, reason="Token expired")
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.disconnect(websocket)

    # ======================== Health Check ========================
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "ibvap-backend"}

    # ======================== Auth ========================
    @app.get("/api/auth/me", tags=["Auth"])
    async def whoami(user: dict = Depends(require_auth)):
        """The caller's resolved application identity (role drives the UI's feature gating)."""
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "username": (user["email"].split("@")[0] if user["email"] else user["user_id"]),
            "role": user["app_role"],
            "allowed_areas": user["allowed_areas"],
        }

    @app.post("/api/auth/logout", tags=["Auth"])
    @limiter.limit("10/minute")
    async def logout(request: Request, user: dict = Depends(require_auth)):
        """Revoke the caller's access token server-side (real logout)."""
        token = user["token"]
        try:
            exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
        except Exception:
            exp = time.time() + 3600
        revoke_token(token, exp)
        return {"status": "logged_out"}

    if is_production:
        logger.info("Running in PRODUCTION mode — API docs disabled")
    else:
        logger.info("Running in DEVELOPMENT mode — API docs enabled at /docs")

    return app


def get_pipeline() -> IBVAPPipeline:
    """Get the global pipeline instance."""
    global pipeline
    return pipeline
