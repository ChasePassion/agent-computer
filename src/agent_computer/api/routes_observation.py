from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from agent_computer.actions import mouse_position
from agent_computer.api.deps import get_registry
from agent_computer.api.live_page import render_live_page
from agent_computer.models.requests import LiveSessionSelectRequest
from agent_computer.runtime import live_output_latest_path, read_json
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(tags=["observation"])

_LIVE_OUTPUT_DEFAULT: dict[str, Any] = {
    "session_id": "active",
    "thread_id": None,
    "turn_id": None,
    "session_mode": "none",
    "thread_status_type": None,
    "thread_active_flags": [],
    "can_send": False,
    "can_interrupt": False,
    "last_error": None,
    "seq": 0,
    "status": "no_output",
    "updated_at": None,
    "heartbeat_at": None,
    "latest_text": None,
    "active_text": None,
    "plan": None,
    "reasoning": None,
    "recent": [],
    "recent_activity": [],
    "truncated": False,
    "stale_after_seconds": 15,
    "source_rollout_path": None,
}

_LIVE_SESSIONS_DEFAULT: dict[str, Any] = {
    "selection_mode": "auto",
    "selected_session_id": None,
    "current_session_id": None,
    "current_turn_id": None,
    "items": [],
}


def _normalize_mode(value: str | None, *, default: Literal["preview", "grid"]) -> Literal["preview", "grid"]:
    if value in {"preview", "grid"}:
        return value
    if value is None:
        return default
    raise HTTPException(status_code=400, detail=f"Unsupported observation mode: {value}")


def _normalize_grid_only_mode(value: str | None) -> Literal["grid"]:
    if value in {None, "grid"}:
        return "grid"
    raise HTTPException(status_code=400, detail="AI-facing observation endpoints only support mode=grid.")


def _require_token(
    token: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> str:
    expected = registry.observation.token()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid observation token.")
    return token


@router.get("/live", response_class=HTMLResponse)
def live_page(
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
) -> HTMLResponse:
    initial_mode = _normalize_mode(mode, default="preview")
    return HTMLResponse(content=render_live_page(token=token, initial_mode=initial_mode))


@router.get("/live/frame.jpg", name="live_observation_image")
def live_image(
    request: Request,
    _: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> FileResponse:
    normalized_mode = _normalize_mode(mode, default="grid")
    try:
        image_path = registry.observation.latest_live_image_path(normalized_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/live/frame.json")
def live_json(
    request: Request,
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    normalized_mode = _normalize_mode(mode, default="grid")
    response_payload = _build_live_frame_payload(
        request=request,
        token=token,
        mode=normalized_mode,
        registry=registry,
    )
    return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/live/state.json")
def live_state_json(
    request: Request,
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    normalized_mode = _normalize_mode(mode, default="preview")
    payload = {
        "frame": _build_live_frame_payload(request=request, token=token, mode=normalized_mode, registry=registry),
        "output": _build_live_output_payload(registry),
        "sessions": _build_live_sessions_payload(registry),
    }
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/live/session/select")
def live_session_select(
    request: LiveSessionSelectRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    watcher = getattr(registry, "codex_session_watcher", None)
    if watcher is None or not hasattr(watcher, "select_session"):
        raise HTTPException(status_code=503, detail="Live session switching is unavailable.")
    try:
        payload = watcher.select_session(request.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown live session: {request.session_id}") from exc
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/observation/latest.jpg", name="observation_latest_image")
def latest_image(
    request: Request,
    _: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> FileResponse:
    normalized_mode = _normalize_grid_only_mode(mode)
    try:
        image_path = registry.observation.latest_image_path(normalized_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/observation/latest.json")
def latest_json(
    request: Request,
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    normalized_mode = _normalize_grid_only_mode(mode)
    payload = registry.observation.latest(normalized_mode)
    if payload is None:
        raise HTTPException(status_code=503, detail=f"No latest observation frame available for mode: {normalized_mode}")
    response_payload = dict(payload)
    response_payload["image_url"] = _relative_url_for(
        request,
        route_name="observation_latest_image",
        token=token,
        mode=normalized_mode,
    )
    return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/observation/mouse.json")
def mouse_json(
    _: str = Depends(_require_token),
) -> JSONResponse:
    x, y = mouse_position()
    payload = {
        "x": x,
        "y": y,
        "coordinate_system": "screen-absolute-grid",
        "origin": [0, 0],
    }
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


def _build_live_frame_payload(
    *,
    request: Request,
    token: str,
    mode: Literal["preview", "grid"],
    registry: ServiceRegistry,
) -> dict[str, object]:
    payload = registry.observation.latest(mode)
    if payload is None:
        raise HTTPException(status_code=503, detail=f"No latest observation frame available for mode: {mode}")
    response_payload = dict(payload)
    response_payload["image_url"] = _relative_url_for(
        request,
        route_name="live_observation_image",
        token=token,
        mode=mode,
    )
    return response_payload


def _relative_url_for(
    request: Request,
    *,
    route_name: str,
    token: str,
    mode: str,
) -> str:
    route_url = request.url_for(route_name)
    return f"{route_url.path}?token={token}&mode={mode}"


def _build_live_output_payload(registry: ServiceRegistry) -> dict[str, Any]:
    live_output = getattr(registry, "live_output", None)
    if live_output is not None and hasattr(live_output, "snapshot"):
        try:
            payload = live_output.snapshot()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            merged = dict(_LIVE_OUTPUT_DEFAULT)
            merged.update(payload)
            if not isinstance(merged.get("thread_active_flags"), list):
                merged["thread_active_flags"] = []
            if not isinstance(merged.get("recent"), list):
                merged["recent"] = []
            if not isinstance(merged.get("recent_activity"), list):
                merged["recent_activity"] = []
            return merged

    path = live_output_latest_path()
    if not path.exists():
        return dict(_LIVE_OUTPUT_DEFAULT)
    try:
        payload = read_json(path)
    except Exception:
        return dict(_LIVE_OUTPUT_DEFAULT)
    if not isinstance(payload, dict):
        return dict(_LIVE_OUTPUT_DEFAULT)
    merged = dict(_LIVE_OUTPUT_DEFAULT)
    merged.update(payload)
    if not isinstance(merged.get("thread_active_flags"), list):
        merged["thread_active_flags"] = []
    if not isinstance(merged.get("recent"), list):
        merged["recent"] = []
    if not isinstance(merged.get("recent_activity"), list):
        merged["recent_activity"] = []
    return merged


def _build_live_sessions_payload(registry: ServiceRegistry) -> dict[str, Any]:
    watcher = getattr(registry, "codex_session_watcher", None)
    if watcher is None or not hasattr(watcher, "sessions_snapshot"):
        return dict(_LIVE_SESSIONS_DEFAULT)
    try:
        payload = watcher.sessions_snapshot()
    except Exception:
        return dict(_LIVE_SESSIONS_DEFAULT)
    if not isinstance(payload, dict):
        return dict(_LIVE_SESSIONS_DEFAULT)
    merged = dict(_LIVE_SESSIONS_DEFAULT)
    merged.update(payload)
    if not isinstance(merged.get("items"), list):
        merged["items"] = []
    return merged
