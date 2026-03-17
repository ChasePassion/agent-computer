from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import ClickRequest, HotkeyRequest, PasteRequest, PressRequest, ScrollRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/live/control", tags=["live-control"])


def _require_token(
    token: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> str:
    expected = registry.observation.token()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid observation token.")
    return token


def _json_response(payload: dict) -> JSONResponse:
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/click")
def live_click(
    request: ClickRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    with registry.execution_lock:
        return _json_response(registry.actions.click(x=request.x, y=request.y, button=request.button, double=request.double))


@router.post("/scroll")
def live_scroll(
    request: ScrollRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    with registry.execution_lock:
        return _json_response(registry.actions.scroll(amount=request.amount))


@router.post("/paste")
def live_paste(
    request: PasteRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    with registry.execution_lock:
        return _json_response(registry.actions.paste(text=request.text, restore_clipboard=request.restore_clipboard))


@router.post("/press")
def live_press(
    request: PressRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    with registry.execution_lock:
        return _json_response(registry.actions.press(key=request.key))


@router.post("/hotkey")
def live_hotkey(
    request: HotkeyRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    with registry.execution_lock:
        return _json_response(registry.actions.hotkey(keys=request.keys))
