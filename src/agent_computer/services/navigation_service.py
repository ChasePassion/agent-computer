from __future__ import annotations

from typing import Any

from agent_computer.actions import open_url
from agent_computer.services.session_service import SessionService
from agent_computer.windowing import focus_window, list_windows


class NavigationService:
    def __init__(self, session: SessionService) -> None:
        self.session = session

    def windows(self) -> list[dict[str, Any]]:
        return [window.to_dict() for window in list_windows()]

    def focus(self, *, title: str, exact: bool = False) -> dict[str, Any]:
        window = focus_window(title, exact=exact)
        payload = window.to_dict()
        self.session.set_last_window(payload)
        return payload

    def open_url(self, *, url: str, restore_clipboard: bool = False) -> dict[str, Any]:
        open_url(url, restore_clipboard=restore_clipboard)
        return {"opened_url": url, "restore_clipboard": restore_clipboard}
