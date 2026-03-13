from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import FocusRequest, OpenUrlRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/windows")
def windows(registry: ServiceRegistry = Depends(get_registry)) -> list[dict]:
    with registry.execution_lock:
        return registry.navigation.windows()


@router.post("/focus")
def focus(request: FocusRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.focus(title=request.title, exact=request.exact)


@router.post("/open-url")
def open_url(request: OpenUrlRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.open_url(url=request.url, restore_clipboard=request.restore_clipboard)
