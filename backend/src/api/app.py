"""
IBVAP — FastAPI Application
AI Microservice: video analytics pipeline + REST API.
Frontend is served separately (Next.js static export behind nginx).
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import jwt
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.auth import issue_media_ticket, require_auth
from src.api.middleware.input_validator import InputValidationMiddleware
from src.api.middleware.security import RequestLoggingMiddleware, SecurityHeadersMiddleware
from src.api.ratelimit import limiter
from src.api.routes import (
    alerts,
    audit,
    cameras,
    events,
    reports,
    snapshots,
    statistics,
    stream,
    tracks,
    watchlists,
    zones,
)
from src.api.routes import evidence as evidence_routes
from src.api.token_revocation import revoke_token
from src.api.websocket import authenticate_ws, ws_manager
from src.database.db import get_database
from src.database.repository import Repository
from src.paths import snapshots_dir

if TYPE_CHECKING:
    from src.pipeline.pipeline import IBVAPPipeline

# Global pipeline reference
pipeline: "IBVAPPipeline | None" = None

_PLACEHOLDER_KEYS = {"", "change-me", "changeme", "test-hmac-key", "dev", "secret", "placeholder"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — start/stop pipeline."""
    logger.info("Starting IBVAP application...")
    loop = asyncio.get_running_loop()
    ws_manager.attach_loop(loop)
    pipeline_enabled = os.getenv("IBVAP_PIPELINE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    app.state.pipeline_status = "starting" if pipeline_enabled else "disabled"
    startup_task = None
    if pipeline_enabled:
        startup_task = asyncio.create_task(
            asyncio.to_thread(_initialize_pipeline, app),
            name="ibvap-pipeline-startup",
        )

    yield

    # Shutdown
    logger.info("Shutting down IBVAP...")
    watchdog = getattr(app.state, "camera_watchdog", None)
    if watchdog is not None:
        # Stop first so it cannot restart cameras that are shutting down.
        await asyncio.to_thread(watchdog.stop)
    if pipeline:
        await asyncio.to_thread(pipeline.stop_all)
    if startup_task is not None and not startup_task.done():
        startup_task.cancel()


def _initialize_pipeline(app: FastAPI) -> None:
    """Load video analytics without delaying or taking down the web API."""
    global pipeline
    candidate = None
    try:
        # This import loads PyTorch/Ultralytics and can be expensive. Keeping it
        # here lets /api/health come online even on a resource-constrained PC.
        from src.pipeline.pipeline import IBVAPPipeline

        candidate = IBVAPPipeline()
        candidate.initialize()

        def alert_callback(alert_data: dict):
            ws_manager.broadcast_sync({"type": "alert", "data": alert_data})

        candidate.alert_engine.register_callback(alert_callback)
        candidate.start_all()
        pipeline = candidate
        app.state.pipeline_status = "ready"
        logger.success("IBVAP video pipeline is ready")

        from src.pipeline.watchdog import CameraWatchdog

        if CameraWatchdog.enabled_from_env():
            watchdog = CameraWatchdog.from_env(candidate)
            watchdog.start()
            app.state.camera_watchdog = watchdog
    except BaseException as exc:
        # MemoryError during ML import/initialisation is recoverable: database
        # APIs and the dashboard should stay available in degraded mode.
        app.state.pipeline_status = "unavailable"
        logger.error(f"Video pipeline unavailable; API will stay online: {exc!r}")
        if candidate is not None:
            try:
                candidate.stop_all()
            except Exception:
                logger.exception("Failed to clean up a partially started pipeline")


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
    snapshots_dir().mkdir(parents=True, exist_ok=True)

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
    app.include_router(watchlists.router, prefix="/api/watchlists", tags=["Watchlists"])
    app.include_router(snapshots.router, prefix="/snapshots", tags=["Snapshots"])

    # Stable integration aliases. Existing unversioned routes remain intact for
    # the current dashboard while external command/control clients can pin v1.
    app.include_router(cameras.router, prefix="/api/v1/cameras", tags=["Cameras v1"])
    app.include_router(events.router, prefix="/api/v1/events", tags=["Events v1"])
    app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts v1"])
    app.include_router(evidence_routes.router, prefix="/api/v1/evidence", tags=["Evidence v1"])

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
    def health_payload(request: Request) -> dict:
        pipeline_status = getattr(request.app.state, "pipeline_status", "starting")
        camera_total = 0
        camera_online = 0
        model_status = {"detector": False, "fine_classifier": False, "face_recognition": False}
        storage = None
        if pipeline is not None:
            stats = pipeline.get_all_stats()
            # The pipeline only instantiates enabled cameras.  Health must report
            # the complete configured camera library (including disabled demos),
            # otherwise the dashboard misleadingly shows 7/7 instead of 7/14.
            camera_online = sum(1 for row in stats.values() if row.get("camera_status") == "online")
            try:
                session = get_database().get_session()
                camera_total = len(Repository(session).get_all_cameras())
                session.close()
            except Exception:
                camera_total = len(stats)
            model_status = {
                "detector": pipeline.detector is not None,
                "fine_classifier": bool(pipeline.fine_classifier and pipeline.fine_classifier.active),
                "face_recognition": bool(pipeline.face_recognizer and pipeline.face_recognizer.active),
            }
            storage = pipeline.alert_engine.get_storage_status()
        ready = pipeline_status == "ready" and camera_total > 0 and camera_online > 0
        return {
            "status": "ok" if ready else "degraded",
            "service": "ibvap-backend",
            "api": "online",
            "pipeline": pipeline_status,
            "ready": ready,
            "cameras": {"online": camera_online, "total": camera_total},
            "models": model_status,
            "storage": storage,
            "persistence_enabled": os.getenv("IBVAP_PERSIST_EVENTS", "true").strip().lower()
            not in {"0", "false", "no", "off"},
        }

    @app.get("/api/health/live")
    async def liveness():
        return {"status": "ok", "service": "ibvap-backend"}

    @app.get("/api/health")
    async def health_check(request: Request):
        return health_payload(request)

    @app.get("/api/health/ready")
    async def readiness(request: Request):
        payload = health_payload(request)
        return JSONResponse(payload, status_code=200 if payload["ready"] else 503)

    @app.get("/api/health/models")
    async def model_health():
        if pipeline is None:
            return {"models": [], "pipeline": "unavailable"}
        return {"models": pipeline.model_registry.snapshot(), "pipeline": "ready"}

    @app.get("/api/v1/health")
    async def versioned_health(request: Request):
        return health_payload(request)

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

    @app.post("/api/auth/media-ticket", tags=["Auth"])
    async def media_ticket(user: dict = Depends(require_auth)):
        return {"ticket": issue_media_ticket(user), "expires_in": 120}

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


def get_pipeline() -> "IBVAPPipeline | None":
    """Get the global pipeline instance."""
    global pipeline
    return pipeline
