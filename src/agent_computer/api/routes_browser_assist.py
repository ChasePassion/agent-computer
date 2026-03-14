from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.browser_assist import (
    BrowserAssistLocateRequest,
    BrowserAssistLocateResponse,
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
