from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_computer.api.deps import get_registry
from agent_computer.models.uia import UIAActRequest, UIALocateRequest, UIAObserveRequest
from agent_computer.services.registry import ServiceRegistry
from agent_computer.uia import (
    UIAElementNotFoundError,
    UIAStaleElementReferenceError,
    UIAutomationError,
    UIAutomationUnavailableError,
)


router = APIRouter(prefix="/uia", tags=["uia"])


def _raise_http_error(exc: UIAutomationError) -> None:
    if isinstance(exc, UIAutomationUnavailableError):
        status_code = 503
        retry_disposition = "fail_fast"
    elif isinstance(exc, UIAElementNotFoundError):
        status_code = 404
        retry_disposition = "reacquire_target"
    elif isinstance(exc, UIAStaleElementReferenceError):
        status_code = 409
        retry_disposition = "reacquire_target"
    else:
        status_code = 422
        retry_disposition = "fail_fast"
    raise HTTPException(
        status_code=status_code,
        detail={"message": str(exc), "retryDisposition": retry_disposition},
    ) from exc


@router.post("/locate")
def uia_locate(
    request: UIALocateRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict[str, object]:
    try:
        return registry.uia.locate(
            window_handle=request.window_handle,
            locator=request.locator,
            scope=request.scope,
            max_results=request.max_results,
        )
    except UIAutomationError as exc:
        _raise_http_error(exc)


@router.post("/observe")
def uia_observe(
    request: UIAObserveRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict[str, object]:
    try:
        return registry.uia.observe(request.nodeRef.model_dump())
    except UIAutomationError as exc:
        _raise_http_error(exc)


@router.post("/act")
def uia_act(
    request: UIAActRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict[str, object]:
    try:
        return registry.uia.act(
            request.nodeRef.model_dump(),
            action=request.action,
            value=request.value,
            verify=None if request.verify is None else request.verify.model_dump(),
            expected_bounds=request.expected_bounds,
            layout_version=request.layout_version,
        )
    except UIAutomationError as exc:
        _raise_http_error(exc)
