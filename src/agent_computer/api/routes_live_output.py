from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import LiveOutputEventRequest, LiveOutputStatusRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/internal/live-output", tags=["live-output"])


@router.get("")
def show_live_output(registry: ServiceRegistry = Depends(get_registry)) -> JSONResponse:
    payload = registry.live_output.snapshot()
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/events")
def append_live_output_event(
    request: LiveOutputEventRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    payload = registry.live_output.append_event(
        kind=request.kind,
        text=request.text,
        created_at=request.created_at,
        status=request.status,
        session_id=request.session_id,
        source_rollout_path=request.source_rollout_path,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/status")
def set_live_output_status(
    request: LiveOutputStatusRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    payload = registry.live_output.set_status(
        request.value,
        updated_at=request.updated_at,
        heartbeat_at=request.updated_at,
        session_id=request.session_id,
        source_rollout_path=request.source_rollout_path,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/reset")
def reset_live_output(
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    payload = registry.live_output.reset()
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
