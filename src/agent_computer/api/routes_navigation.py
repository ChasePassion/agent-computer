from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import BrowserOpenUrlRequest, FocusRequest, MaximizeRequest
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


@router.post("/maximize")
def maximize(request: MaximizeRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.maximize(title=request.title, exact=request.exact)


@router.post("/browser-open-url")
def browser_open_url(request: BrowserOpenUrlRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.browser_open_url(url=request.url, restore_clipboard=request.restore_clipboard)


@router.post("/browser-current-url")
def browser_current_url(registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.browser_current_url()


@router.post("/browser-back")
def browser_back(registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.browser_back()


@router.post("/browser-forward")
def browser_forward(registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.browser_forward()


@router.post("/browser-refresh")
def browser_refresh(registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.navigation.browser_refresh()
