"""
IBVAP — Intelligent Border Video Analytics Platform
Main entry point.
"""

import os
import sys
import argparse
from pathlib import Path

import uvicorn
from loguru import logger
from dotenv import load_dotenv


def setup_logging():
    """Configure loguru logging."""
    log_dir = Path("./outputs/logs")
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
    parser = argparse.ArgumentParser(
        description="IBVAP — Intelligent Border Video Analytics Platform"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--config", default="./configs", help="Config directory path")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Setup logging
    setup_logging()

    # Create required directories
    output_base = os.getenv("IBVAP_OUTPUT_DIR", "./outputs")
    model_base = os.getenv("IBVAP_MODEL_DIR", "./models")
    data_base = os.getenv("IBVAP_DATA_DIR", "./data")

    for d in [f"{output_base}/snapshots", f"{output_base}/logs", f"{output_base}/metrics",
              f"{output_base}/videos", f"{model_base}/detection", f"{model_base}/face",
              f"{model_base}/anpr", f"{model_base}/risk", f"{data_base}/custom"]:
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
    uvicorn.run(
        "src.api.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level="info" if not args.debug else "debug",
    )


if __name__ == "__main__":
    main()
