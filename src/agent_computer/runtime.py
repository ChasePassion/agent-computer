from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
OBSERVATION_DIR = ARTIFACTS_DIR / "observation"
AGENT_DIR = PROJECT_ROOT / ".agent"
DEFAULT_HOST = os.getenv("AGENT_COMPUTER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("AGENT_COMPUTER_PORT", "37688"))
DEFAULT_STARTUP_TIMEOUT_SEC = float(os.getenv("AGENT_COMPUTER_STARTUP_TIMEOUT_SEC", "15"))
DEFAULT_HTTP_TIMEOUT_SEC = float(os.getenv("AGENT_COMPUTER_HTTP_TIMEOUT_SEC", "180"))
DEFAULT_OBSERVATION_INTERVAL_SEC = float(os.getenv("AGENT_COMPUTER_OBSERVATION_INTERVAL_SEC", "1.0"))
DEFAULT_OBSERVATION_GRID_SIZE = int(os.getenv("AGENT_COMPUTER_OBSERVATION_GRID_SIZE", "50"))
DEFAULT_OBSERVATION_JPEG_QUALITY = int(os.getenv("AGENT_COMPUTER_OBSERVATION_JPEG_QUALITY", "75"))
DEFAULT_OBSERVATION_RETENTION_DAYS = int(os.getenv("AGENT_COMPUTER_OBSERVATION_RETENTION_DAYS", "7"))
DEFAULT_OBSERVATION_RETENTION_MAX_FILES = int(os.getenv("AGENT_COMPUTER_OBSERVATION_RETENTION_MAX_FILES", "200"))
DEFAULT_OBSERVATION_PUBLIC_BASE_URL = os.getenv("AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL", "").strip()


def ensure_runtime_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_DIR.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_capture_path(prefix: str = "capture", suffix: str = ".png") -> Path:
    ensure_runtime_dirs()
    return ARTIFACTS_DIR / f"{prefix}_{timestamp()}{suffix}"


def write_json(path: str | Path, payload: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str | Path, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def metadata_sidecar_path(image_path: str | Path) -> Path:
    return Path(str(image_path) + ".meta.json")


def write_capture_sidecar(capture_payload: dict[str, Any]) -> None:
    image_path = capture_payload.get("image_path")
    if not image_path:
        return
    write_json(metadata_sidecar_path(image_path), capture_payload)


def daemon_base_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def observation_token_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "observation.json"


def observation_remote_config_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "observation.remote.json"


def preview_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "preview_latest.jpg"


def grid_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "grid_latest.jpg"
