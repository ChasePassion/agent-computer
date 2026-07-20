from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
from agent_computer.retry import RetryDisposition, RetryDispositionError
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/browser-assist", tags=["browser-assist"])


def _raise_http_error(exc: RetryDispositionError) -> None:
    if exc.details.get("outcome") == "unknown" or "timed out" in str(exc).casefold():
        status_code = 504
    elif exc.retry_disposition == RetryDisposition.REACQUIRE_TARGET:
        status_code = 409
    elif exc.retry_disposition == RetryDisposition.CONTEXT_LOST:
        status_code = 503
    else:
        status_code = 422
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": str(exc),
            "retryDisposition": exc.retry_disposition.value,
            "details": exc.details,
        },
    ) from exc


@router.get("/status", response_model=BrowserAssistStatusResponse)
def browser_assist_status(registry: ServiceRegistry = Depends(get_registry)) -> BrowserAssistStatusResponse:
    return registry.browser_assist.status()


@router.post("/locate", response_model=BrowserAssistLocateResponse)
async def browser_assist_locate(
    request: BrowserAssistLocateRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistLocateResponse:
    try:
        return await registry.browser_assist.locate(request)
    except RetryDispositionError as exc:
        _raise_http_error(exc)


@router.post("/observe", response_model=BrowserAssistObserveResponse)
async def browser_assist_observe(
    request: BrowserAssistObserveRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistObserveResponse:
    try:
        return await registry.browser_assist.observe(request)
    except RetryDispositionError as exc:
        _raise_http_error(exc)


@router.post("/act", response_model=BrowserAssistActResponse)
async def browser_assist_act(
    request: BrowserAssistActRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> BrowserAssistActResponse:
    try:
        return await registry.browser_assist.act(request)
    except RetryDispositionError as exc:
        _raise_http_error(exc)
