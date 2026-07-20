from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
OBSERVATION_DIR = ARTIFACTS_DIR / "observation"
LIVE_OUTPUT_DIR = ARTIFACTS_DIR / "live-output"
AGENT_DIR = PROJECT_ROOT / ".agent"
DEFAULT_HOST = os.getenv("AGENT_COMPUTER_HOST", "127.0.0.1")
DEFAULT_BIND_HOST = os.getenv("AGENT_COMPUTER_BIND_HOST", DEFAULT_HOST)
DEFAULT_PORT = int(os.getenv("AGENT_COMPUTER_PORT", "37688"))
DEFAULT_STARTUP_TIMEOUT_SEC = float(os.getenv("AGENT_COMPUTER_STARTUP_TIMEOUT_SEC", "15"))
DEFAULT_HTTP_TIMEOUT_SEC = float(os.getenv("AGENT_COMPUTER_HTTP_TIMEOUT_SEC", "180"))
DEFAULT_OBSERVATION_INTERVAL_SEC = float(os.getenv("AGENT_COMPUTER_OBSERVATION_INTERVAL_SEC", "1.0"))
DEFAULT_OBSERVATION_TARGET = os.getenv("AGENT_COMPUTER_OBSERVATION_TARGET", "virtual-screen").strip().lower()
if DEFAULT_OBSERVATION_TARGET not in {"primary-screen", "virtual-screen"}:
    DEFAULT_OBSERVATION_TARGET = "virtual-screen"
DEFAULT_OBSERVATION_GRID_SIZE = int(os.getenv("AGENT_COMPUTER_OBSERVATION_GRID_SIZE", "50"))
DEFAULT_OBSERVATION_JPEG_QUALITY = int(os.getenv("AGENT_COMPUTER_OBSERVATION_JPEG_QUALITY", "75"))
DEFAULT_OBSERVATION_RETENTION_DAYS = int(os.getenv("AGENT_COMPUTER_OBSERVATION_RETENTION_DAYS", "7"))
DEFAULT_OBSERVATION_RETENTION_MAX_FILES = int(os.getenv("AGENT_COMPUTER_OBSERVATION_RETENTION_MAX_FILES", "200"))
DEFAULT_LIVE_IMAGE_MAX_DIMENSION = int(os.getenv("AGENT_COMPUTER_LIVE_IMAGE_MAX_DIMENSION", "1600"))
DEFAULT_LIVE_IMAGE_JPEG_QUALITY = int(os.getenv("AGENT_COMPUTER_LIVE_IMAGE_JPEG_QUALITY", "45"))
DEFAULT_OBSERVATION_PUBLIC_BASE_URL = os.getenv("AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL", "").strip()
DEFAULT_PUBLIC_PREFERRED = os.getenv("AGENT_COMPUTER_PUBLIC_PREFERRED", "funnel").strip().lower() or "funnel"
DEFAULT_FUNNEL_HTTPS_PORT = int(os.getenv("AGENT_COMPUTER_FUNNEL_HTTPS_PORT", "443"))
DEFAULT_BROWSER_ASSIST_WS_PATH = os.getenv("AGENT_COMPUTER_BROWSER_ASSIST_WS_PATH", "/ws/browser-assist")
DEFAULT_CODEX_HOME = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
DEFAULT_CODEX_TARGET_CWD = Path(os.getenv("AGENT_COMPUTER_CODEX_TARGET_CWD", str(PROJECT_ROOT))).expanduser().resolve()
DEFAULT_CODEX_SESSION_POLL_INTERVAL_SEC = float(os.getenv("AGENT_COMPUTER_CODEX_SESSION_POLL_INTERVAL_SEC", "0.75"))
DEFAULT_LIVE_OUTPUT_MAX_ITEMS = int(os.getenv("AGENT_COMPUTER_LIVE_OUTPUT_MAX_ITEMS", "12"))
DEFAULT_LIVE_OUTPUT_MAX_CHARS = int(os.getenv("AGENT_COMPUTER_LIVE_OUTPUT_MAX_CHARS", "6000"))
DEFAULT_LIVE_OUTPUT_STALE_AFTER_SEC = int(os.getenv("AGENT_COMPUTER_LIVE_OUTPUT_STALE_AFTER_SEC", "15"))


def ensure_runtime_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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


def observation_urls_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "observation.urls.json"


def observation_funnel_state_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "observation.funnel.json"


def observation_tunnel_state_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "observation.tunnel.state.json"


def browser_assist_config_path() -> Path:
    ensure_runtime_dirs()
    return AGENT_DIR / "browser_assist.json"


def preview_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "preview_latest.jpg"


def grid_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "grid_latest.jpg"


def live_preview_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "live_preview_latest.jpg"


def live_grid_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "live_grid_latest.jpg"


def zoom_latest_path() -> Path:
    ensure_runtime_dirs()
    return OBSERVATION_DIR / "zoom_latest.jpg"


def live_output_latest_path() -> Path:
    ensure_runtime_dirs()
    return LIVE_OUTPUT_DIR / "latest.json"


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_funnel_public_base_url() -> str | None:
    payload = _read_json_if_exists(observation_funnel_state_path())
    value = str(payload.get("public_base_url", "")).strip() if payload else ""
    return _normalize_base_url(value) if value else None


def _read_relay_public_base_url() -> str | None:
    if not DEFAULT_OBSERVATION_PUBLIC_BASE_URL:
        return None
    payload = _read_json_if_exists(observation_tunnel_state_path())
    if payload and payload.get("cleanup_pending") is False:
        return _normalize_base_url(DEFAULT_OBSERVATION_PUBLIC_BASE_URL)
    return None


def _read_public_endpoints() -> dict[str, str]:
    endpoints: dict[str, str] = {}
    funnel_base = _read_funnel_public_base_url()
    if funnel_base:
        endpoints["funnel"] = funnel_base
    relay_base = _read_relay_public_base_url()
    if relay_base:
        endpoints["relay"] = relay_base
    return endpoints


def _pick_default_public_endpoint(public_endpoints: dict[str, str]) -> tuple[str, str] | None:
    preferred = DEFAULT_PUBLIC_PREFERRED
    if preferred in public_endpoints:
        return preferred, public_endpoints[preferred]
    if "funnel" in public_endpoints:
        return "funnel", public_endpoints["funnel"]
    if "relay" in public_endpoints:
        return "relay", public_endpoints["relay"]
    return None


def _observation_url_bundle(*, base_url: str, token: str) -> dict[str, str]:
    normalized_base_url = _normalize_base_url(base_url)
    return {
        "base_url": normalized_base_url,
        "live_url": f"{normalized_base_url}/live?token={token}",
        "mouse_url": f"{normalized_base_url}/observation/mouse.json?token={token}",
        "preview_image_url": f"{normalized_base_url}/live/frame.jpg?token={token}&mode=preview",
        "preview_meta_url": f"{normalized_base_url}/live/frame.json?token={token}&mode=preview",
        "grid_image_url": f"{normalized_base_url}/observation/latest.jpg?token={token}&mode=grid",
        "grid_meta_url": f"{normalized_base_url}/observation/latest.json?token={token}&mode=grid",
    }


def build_observation_urls_manifest(
    *,
    token: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    public_base_url: str | None = None,
) -> dict[str, Any]:
    local = _observation_url_bundle(base_url=daemon_base_url(host, port), token=token)
    public_endpoints = _read_public_endpoints()
    if public_base_url:
        public_endpoints["relay"] = _normalize_base_url(public_base_url)
    default_public_choice = _pick_default_public_endpoint(public_endpoints)

    manifest: dict[str, Any] = {
        "token": token,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "defaults": {
            "human_live_url": local["live_url"],
            "model_image_url": local["grid_image_url"],
            "model_meta_url": local["grid_meta_url"],
            "model_mouse_url": local["mouse_url"],
        },
        "local": local,
        "public_variants": {},
        "human_default_url": local["live_url"],
        "human_live_url": local["live_url"],
        "human_preview_url": local["preview_image_url"],
        "human_grid_url": local["grid_image_url"],
        "model_default_image_url": local["grid_image_url"],
        "model_default_meta_url": local["grid_meta_url"],
        "model_mouse_url": local["mouse_url"],
    }

    for name, base_url in public_endpoints.items():
        bundle = _observation_url_bundle(base_url=base_url, token=token)
        manifest["public_variants"][name] = bundle
        manifest[f"public_{name}"] = bundle

    if default_public_choice:
        default_public_name, default_public_base = default_public_choice
        public = _observation_url_bundle(base_url=default_public_base, token=token)
        manifest["public"] = public
        manifest["public_default_name"] = default_public_name
        manifest["public_human_live_url"] = public["live_url"]
        manifest["public_human_preview_url"] = public["preview_image_url"]
        manifest["public_human_grid_url"] = public["grid_image_url"]
        manifest["public_model_default_image_url"] = public["grid_image_url"]
        manifest["public_model_default_meta_url"] = public["grid_meta_url"]
        manifest["public_model_mouse_url"] = public["mouse_url"]
        manifest["defaults"] = {
            "human_live_url": public["live_url"],
            "model_image_url": public["grid_image_url"],
            "model_meta_url": public["grid_meta_url"],
            "model_mouse_url": public["mouse_url"],
        }
        manifest["human_default_url"] = public["live_url"]
        manifest["model_default_image_url"] = public["grid_image_url"]
        manifest["model_default_meta_url"] = public["grid_meta_url"]
        manifest["model_mouse_url"] = public["mouse_url"]

    return manifest


def write_observation_urls_manifest(
    *,
    token: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    public_base_url: str | None = None,
) -> dict[str, Any]:
    payload = build_observation_urls_manifest(
        token=token,
        host=host,
        port=port,
        public_base_url=public_base_url,
    )
    write_json(observation_urls_path(), payload)
    return payload
