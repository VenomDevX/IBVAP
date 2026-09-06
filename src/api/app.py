"""
IBVAP — FastAPI Application
Main backend application with routing, static files, and templates.
"""

import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from loguru import logger

from src.api.routes import cameras, events, alerts, zones, tracks, statistics, auth, stream
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
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    static_dir = Path(__file__).parent.parent.parent / "dashboard" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Snapshots directory
    snapshots_dir = Path("./outputs/snapshots")
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=str(snapshots_dir)), name="snapshots")

    # Templates
    templates_dir = Path(__file__).parent.parent.parent / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir)) if templates_dir.exists() else None

    # Store references in app state
    app.state.templates = templates

    # ======================== API Routes ========================
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
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
                # Handle client messages if needed (e.g., ping)
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)

    # ======================== Page Routes ========================
    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "dashboard.html")
        return HTMLResponse("<h1>IBVAP Dashboard</h1><p>Templates not found.</p>")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "login.html")
        return HTMLResponse("<h1>Login</h1>")

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "signup.html")
        return HTMLResponse("<h1>Sign Up</h1>")

    @app.get("/cameras", response_class=HTMLResponse)
    async def cameras_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "cameras.html")
        return HTMLResponse("<h1>Cameras</h1>")

    @app.get("/alerts-page", response_class=HTMLResponse)
    async def alerts_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "alerts.html")
        return HTMLResponse("<h1>Alerts</h1>")

    @app.get("/events-page", response_class=HTMLResponse)
    async def events_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "events.html")
        return HTMLResponse("<h1>Events</h1>")

    @app.get("/events/{event_id}", response_class=HTMLResponse)
    async def event_detail_page(request: Request, event_id: str):
        if templates:
            return templates.TemplateResponse(
                request, "event_detail.html", {"event_id": event_id}
            )
        return HTMLResponse(f"<h1>Event {event_id}</h1>")

    @app.get("/zones-page", response_class=HTMLResponse)
    async def zones_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "zones.html")
        return HTMLResponse("<h1>Zones</h1>")

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        if templates:
            return templates.TemplateResponse(request, "settings.html")
        return HTMLResponse("<h1>Settings</h1>")

    return app


def get_pipeline() -> IBVAPPipeline:
    """Get the global pipeline instance."""
    global pipeline
    return pipeline
