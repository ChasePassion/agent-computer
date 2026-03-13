from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import ClickElementRequest, ClickRequest, HotkeyRequest, MoveRequest, PasteRequest, PressRequest, ScrollRequest, TypeRequest
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


@router.post("/click-element")
def click_element(
    request: ClickElementRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict:
    with registry.execution_lock:
        return registry.actions.click_element(
            json_file=request.json_file,
            index=request.index,
            button=request.button,
            double=request.double,
        )


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
