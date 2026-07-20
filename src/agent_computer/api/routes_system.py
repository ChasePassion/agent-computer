from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent_computer import __version__
from agent_computer.api.deps import get_registry
from agent_computer.display import get_display_layout
from agent_computer.models.responses import DaemonHealthResponse
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=DaemonHealthResponse)
def health(request: Request, registry: ServiceRegistry = Depends(get_registry)) -> DaemonHealthResponse:
    snapshot = registry.session.snapshot()
    return DaemonHealthResponse(
        status="ok",
        version=__version__,
        host=request.app.state.host,
        port=request.app.state.port,
        **snapshot,
    )


@router.get("/version")
def version() -> dict[str, str]:
    return {"version": __version__}


@router.get("/metrics")
def metrics(registry: ServiceRegistry = Depends(get_registry)) -> dict:
    return registry.metrics.snapshot()


@router.get("/display-layout")
def display_layout() -> dict[str, object]:
    return get_display_layout()


@router.post("/shutdown")
def shutdown(request: Request) -> dict[str, str]:
    server = request.app.state.server
    server.should_exit = True
    return {"status": "shutting_down"}
