from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import ClickRequest, HotkeyRequest, MoveRequest, PasteRequest, PressRequest, ScrollRequest, TypeRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/move")
def move(request: MoveRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.move(x=request.x, y=request.y, duration=request.duration)


@router.post("/click")
def click(request: ClickRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.click(x=request.x, y=request.y, button=request.button, double=request.double)


@router.post("/scroll")
def scroll(request: ScrollRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.scroll(amount=request.amount)


@router.post("/type")
def type_text(request: TypeRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.type_text(text=request.text, interval=request.interval)


@router.post("/paste")
def paste(request: PasteRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.paste(text=request.text, restore_clipboard=request.restore_clipboard)


@router.post("/press")
def press(request: PressRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.press(key=request.key)


@router.post("/hotkey")
def hotkey(request: HotkeyRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.actions.hotkey(keys=request.keys)
