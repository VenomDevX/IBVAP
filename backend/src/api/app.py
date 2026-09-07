"""
IBVAP — FastAPI Application
AI Microservice: video analytics pipeline + REST API.
Frontend is served separately by React/Vite.
"""

import os
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from loguru import logger

from src.api.routes import cameras, events, alerts, zones, tracks, statistics, stream
from src.api.auth import _verify_token
from src.api.websocket import ws_manager
from src.pipeline.pipeline import IBVAPPipeline

# Global pipeline reference
pipeline: IBVAPPipeline = None

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


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

    # Start camera pipelines
    pipeline.start_all()

    yield

    # Shutdown
    logger.info("Shutting down IBVAP...")
    if pipeline:
        pipeline.stop_all()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="IBVAP — Intelligent Border Video Analytics Platform",
        description="AI-Based Video Analytics for Border Surveillance",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS — restrict to allowed frontend origins
    cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:80,http://127.0.0.1:3000"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Snapshots directory (for evidence images)
    snapshots_dir = Path("./outputs/snapshots")
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=str(snapshots_dir)), name="snapshots")

    # ======================== API Routes ========================
    app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
    app.include_router(events.router, prefix="/api/events", tags=["Events"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
    app.include_router(zones.router, prefix="/api/zones", tags=["Zones"])
    app.include_router(tracks.router, prefix="/api/tracks", tags=["Tracks"])
    app.include_router(statistics.router, prefix="/api/statistics", tags=["Statistics"])
    app.include_router(stream.router, prefix="/api/stream", tags=["Video Stream"])

    # ======================== WebSocket ========================
    @app.websocket("/ws/alerts")
    async def websocket_alerts(websocket: WebSocket):
        # Authenticate via query param: /ws/alerts?token=<jwt>
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Missing auth token")
            return
        try:
            _verify_token(token)
        except Exception:
            await websocket.close(code=4003, reason="Invalid or expired token")
            return

        await ws_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)

    # ======================== Health Check ========================
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "ibvap-backend"}

    return app


def get_pipeline() -> IBVAPPipeline:
    """Get the global pipeline instance."""
    global pipeline
    return pipeline

