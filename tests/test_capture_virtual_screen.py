from __future__ import annotations

from agent_computer import capture
from agent_computer.models.requests import CaptureRequest


class _FakeMssContext:
    monitors = [
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
    ]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_virtual_screen_region_uses_mss_all_monitors_entry(monkeypatch) -> None:
    monkeypatch.setattr(capture.mss, "mss", _FakeMssContext)

    assert capture._get_virtual_monitor_region() == {
        "left": -1920,
        "top": 0,
        "width": 3840,
        "height": 1080,
    }


def test_capture_request_accepts_virtual_screen_target() -> None:
    request = CaptureRequest.model_validate({"target": "virtual-screen"})

    assert request.target == "virtual-screen"
