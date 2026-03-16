from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import LiveSessionMessageRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(tags=["live-session"])


def _require_token(
    token: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> str:
    expected = registry.observation.token()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid observation token.")
    return token


@router.post("/live/session/message")
def live_session_message(
    request: LiveSessionMessageRequest,
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    payload = registry.codex_managed_session.send_message(request.message)
    payload["message_length"] = len(request.message)
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/live/session/interrupt")
def live_session_interrupt(
    _: str = Depends(_require_token),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    payload = registry.codex_managed_session.interrupt()
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
