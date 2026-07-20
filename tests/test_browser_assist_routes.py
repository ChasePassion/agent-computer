from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.deps import get_registry
from agent_computer.api.routes_browser_assist import router
from agent_computer.retry import RetryDisposition, RetryDispositionError


class AmbiguousTimeoutBrowserAssist:
    async def act(self, _request):
        raise RetryDispositionError(
            "Browser Assist act request timed out. The action may have executed.",
            retry_disposition=RetryDisposition.FAIL_FAST,
            details={
                "requestType": "act",
                "outcome": "unknown",
                "actionMayHaveExecuted": True,
            },
        )


class StubRegistry:
    browser_assist = AmbiguousTimeoutBrowserAssist()


def test_browser_assist_route_preserves_ambiguous_action_timeout_classification() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_registry] = lambda: StubRegistry()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/browser-assist/act",
            json={"action": "navigate", "url": "https://example.test/next"},
        )

    assert response.status_code == 504
    assert response.json()["detail"] == {
        "message": "Browser Assist act request timed out. The action may have executed.",
        "retryDisposition": "fail_fast",
        "details": {
            "requestType": "act",
            "outcome": "unknown",
            "actionMayHaveExecuted": True,
        },
    }
