from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from agent_computer.actions import mouse_position
from agent_computer.api.deps import get_registry
from agent_computer.api.live_page import render_live_page
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(tags=["observation"])


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
    payload = {"frame": _build_live_frame_payload(request=request, token=token, mode=normalized_mode, registry=registry)}
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
