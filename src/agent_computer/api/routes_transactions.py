from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_computer.api.deps import get_registry
from agent_computer.models.transactions import ActAndObserveRequest, BatchActAndObserveRequest
from agent_computer.services.registry import ServiceRegistry
from agent_computer.services.action_coordinator import (
    ActionOutcomeUnknownError,
    ActionPreconditionError,
)


router = APIRouter(prefix="/actions", tags=["action-transactions"])


@router.post("/act-and-observe")
def act_and_observe(
    request: ActAndObserveRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict:
    try:
        return registry.action_coordinator.execute(request)
    except ActionPreconditionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "retryDisposition": "reacquire_target"},
        ) from exc
    except ActionOutcomeUnknownError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "retryDisposition": "fail_fast",
                "details": exc.details,
            },
        ) from exc


@router.post("/batch-act-and-observe")
def batch_act_and_observe(
    request: BatchActAndObserveRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict:
    try:
        return registry.action_coordinator.execute_batch(request)
    except ActionPreconditionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "retryDisposition": "reacquire_target"},
        ) from exc
    except ActionOutcomeUnknownError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "retryDisposition": "fail_fast",
                "details": exc.details,
            },
        ) from exc
