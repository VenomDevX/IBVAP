"""Canonical runtime paths, independent of the process working directory."""

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def backend_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else BACKEND_ROOT / path).resolve()


def runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    return backend_path(configured if configured else default_relative)


def output_dir() -> Path:
    return runtime_path("IBVAP_OUTPUT_DIR", "outputs")


def snapshots_dir() -> Path:
    configured = os.getenv("IBVAP_SNAPSHOTS_DIR")
    if configured:
        return runtime_path("IBVAP_SNAPSHOTS_DIR", "outputs/snapshots")
    return (output_dir() / "snapshots").resolve()


def config_dir() -> Path:
    return runtime_path("IBVAP_CONFIG_DIR", "configs")


def default_database_url() -> str:
    return f"sqlite:///{(BACKEND_ROOT / 'ibvap.db').as_posix()}"
