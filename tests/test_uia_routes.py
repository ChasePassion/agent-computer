from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.routes_uia import router as uia_router


class StubUIA:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def locate(self, **kwargs):
        self.calls.append(("locate", kwargs))
        return {"backend": "uia", "count": 1, "matches": []}

    def observe(self, node_ref):
        self.calls.append(("observe", node_ref))
        return {"backend": "uia", "element": {"nodeRef": node_ref}}

    def act(self, node_ref, **kwargs):
        self.calls.append(("act", {"node_ref": node_ref, **kwargs}))
        return {"backend": "uia", "performed": True, "verificationStatus": "not_requested"}


def test_uia_routes_forward_json_friendly_requests() -> None:
    app = FastAPI()
    uia = StubUIA()
    app.state.registry = SimpleNamespace(uia=uia)
    app.include_router(uia_router)

    node_ref = {"backend": "uia", "runtime_id": [42, 7], "window_handle": 101}
    with TestClient(app) as client:
        locate = client.post(
            "/uia/locate",
            json={"window_handle": 101, "locator": {"name": "Save"}, "max_results": 5},
        )
        observe = client.post("/uia/observe", json={"nodeRef": node_ref})
        act = client.post("/uia/act", json={"nodeRef": node_ref, "action": "invoke"})

    assert locate.status_code == 200
    assert observe.status_code == 200
    assert act.status_code == 200
    assert [name for name, _payload in uia.calls] == ["locate", "observe", "act"]
