from __future__ import annotations

from fastapi import Request

from agent_computer.services.registry import ServiceRegistry


def get_registry(request: Request) -> ServiceRegistry:
    return request.app.state.registry
