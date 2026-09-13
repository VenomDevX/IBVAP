"""
IBVAP — Intelligent Border Video Analytics Platform
Main entry point.
"""

import argparse
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from loguru import logger
from src.paths import output_dir


def setup_logging():
    """Configure loguru logging."""
    log_dir = output_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_dir / "ibvap_{time}.log"),
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )


def main():
    """Main entry point for IBVAP."""
    # Load environment variables FIRST: --port's default below reads IBVAP_PORT,
    # so .env must already be loaded before argparse computes it. Getting this
    # order backwards is what let backend/.env's IBVAP_PORT=8002 silently do
    # nothing for the CLI default while frontend/.env.development's
    # NEXT_PUBLIC_API_BASE correctly pointed at 8002 - the two configs never
    # actually agreed, so a plain `python main.py` (defaulting to 8000) always
    # left the frontend talking to a port nothing was listening on.
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="IBVAP — Intelligent Border Video Analytics Platform"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("IBVAP_PORT", 8000)),
        help="Port to bind (default: $IBVAP_PORT from .env, else 8000)",
    )
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--config", default="./configs", help="Config directory path")

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    # Create required directories
    output_base = str(output_dir())
    model_base = os.getenv("IBVAP_MODEL_DIR", "./models")
    data_base = os.getenv("IBVAP_DATA_DIR", "./data")

    for d in [f"{output_base}/snapshots", f"{output_base}/logs", f"{output_base}/metrics",
              f"{output_base}/videos", f"{model_base}/detection", f"{model_base}/face",
              f"{model_base}/anpr", f"{model_base}/risk", f"{data_base}/demo"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Banner
    env_mode = os.getenv("IBVAP_ENV", "development").upper()
    print(f"""
    ==========================================================
    |                                                        |
    |   IBVAP - Intelligent Border Video Analytics Platform  |
    |   AI-Based Surveillance using Existing CCTV            |
    |   Mode: {env_mode:<45s}|
    |                                                        |
    ==========================================================
    """)

    logger.info(f"Starting IBVAP on {args.host}:{args.port}")
    logger.info(f"Config directory: {args.config}")
    logger.info(f"Dashboard: http://localhost:{args.port}")
    logger.info(f"API Docs: http://localhost:{args.port}/docs")

    # Set config path environment variable
    os.environ["IBVAP_CONFIG_DIR"] = args.config

    # Run FastAPI with Uvicorn
    _trusted_proxy = os.getenv("TRUSTED_PROXY", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "src.api.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level="info" if not args.debug else "debug",
        proxy_headers=_trusted_proxy,
        forwarded_allow_ips="*" if _trusted_proxy else None,
    )


if __name__ == "__main__":
    main()
