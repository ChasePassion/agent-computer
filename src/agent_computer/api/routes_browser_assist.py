from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.browser_assist import (
    BrowserAssistActRequest,
    BrowserAssistActResponse,
    BrowserAssistLocateRequest,
    BrowserAssistLocateResponse,
    BrowserAssistObserveRequest,
    BrowserAssistObserveResponse,
    BrowserAssistStatusResponse,
)
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/browser-assist", tags=["browser-assist"])


@router.get("/status", response_model=BrowserAssistStatusResponse)
def browser_assist_status(registry: ServiceRegistry = Depends(get_registry)) -> BrowserAssistStatusResponse:
    return registry.browser_assist.status()


@router.post("/locate", response_model=BrowserAssistLocateResponse)
async def browser_assist_locate(
    request: BrowserAssistLocateRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistLocateResponse:
    return await registry.browser_assist.locate(request)


@router.post("/observe", response_model=BrowserAssistObserveResponse)
async def browser_assist_observe(
    request: BrowserAssistObserveRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistObserveResponse:
    return await registry.browser_assist.observe(request)


@router.post("/act", response_model=BrowserAssistActResponse)
async def browser_assist_act(
    request: BrowserAssistActRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistActResponse:
    return await registry.browser_assist.act(request)
