from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_computer.api.routes_actions import router as actions_router
from agent_computer.api.routes_browser_assist import router as browser_assist_router
from agent_computer.api.routes_browser_assist_ws import router as browser_assist_ws_router
from agent_computer.api.routes_capture import router as capture_router
from agent_computer.api.routes_live_output import router as live_output_router
from agent_computer.api.routes_navigation import router as navigation_router
from agent_computer.api.routes_observation import router as observation_router
from agent_computer.api.routes_system import router as system_router
from agent_computer.runtime import ensure_runtime_dirs
from agent_computer.services import create_service_registry


def create_app(*, host: str, port: int) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_runtime_dirs()
        app.state.registry = create_service_registry(host=host, port=port)
        app.state.registry.observation.start()
        app.state.registry.codex_session_watcher.start()
        yield
        app.state.registry.codex_session_watcher.stop()
        app.state.registry.observation.stop()

    app = FastAPI(title="Agent Computer Daemon", version="0.1.0", lifespan=lifespan)
    app.state.host = host
    app.state.port = port
    app.state.server = None
    app.include_router(system_router)
    app.include_router(capture_router)
    app.include_router(navigation_router)
    app.include_router(actions_router)
    app.include_router(observation_router)
    app.include_router(live_output_router)
    app.include_router(browser_assist_router)
    app.include_router(browser_assist_ws_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"type": type(exc).__name__, "message": str(exc)}},
        )

    return app
