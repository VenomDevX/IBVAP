"""
IBVAP — FastAPI Application
AI Microservice: video analytics pipeline + REST API.
Frontend is served separately by React/Vite.
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import cameras, events, alerts, zones, tracks, statistics, stream
from src.api.websocket import ws_manager
from src.pipeline.pipeline import IBVAPPipeline

# Global pipeline reference
pipeline: IBVAPPipeline = None


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

    # CORS — allow React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

