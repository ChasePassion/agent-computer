from __future__ import annotations

from typing import Any

from agent_computer.actions import (
    browser_back,
    browser_current_url,
    browser_forward,
    browser_open_url,
    browser_refresh,
)
from agent_computer.services.session_service import SessionService
from agent_computer.windowing import (
    focus_window,
    list_windows,
    maximize_window,
    require_foreground_browser_window,
)


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

    def maximize(self, *, title: str, exact: bool = False) -> dict[str, Any]:
        payload = maximize_window(title, exact=exact)
        self.session.set_last_window(payload)
        return payload

    def browser_open_url(self, *, url: str, restore_clipboard: bool = False) -> dict[str, Any]:
        browser = require_foreground_browser_window()
        browser_open_url(url, restore_clipboard=restore_clipboard)
        self.session.set_last_window(browser)
        return {
            "operation": "browser-open-url",
            "opened_url": url,
            "restore_clipboard": restore_clipboard,
            "window_title": browser["title"],
            "process_name": browser.get("process_name"),
        }

    def browser_current_url(self) -> dict[str, Any]:
        browser = require_foreground_browser_window()
        current_url = browser_current_url()
        self.session.set_last_window(browser)
        return {
            "operation": "browser-current-url",
            "current_url": current_url,
            "window_title": browser["title"],
            "process_name": browser.get("process_name"),
        }

    def browser_back(self) -> dict[str, Any]:
        browser = require_foreground_browser_window()
        browser_back()
        self.session.set_last_window(browser)
        return {
            "operation": "browser-back",
            "keys": ["alt", "left"],
            "window_title": browser["title"],
            "process_name": browser.get("process_name"),
        }

    def browser_forward(self) -> dict[str, Any]:
        browser = require_foreground_browser_window()
        browser_forward()
        self.session.set_last_window(browser)
        return {
            "operation": "browser-forward",
            "keys": ["alt", "right"],
            "window_title": browser["title"],
            "process_name": browser.get("process_name"),
        }

    def browser_refresh(self) -> dict[str, Any]:
        browser = require_foreground_browser_window()
        browser_refresh()
        self.session.set_last_window(browser)
        return {
            "operation": "browser-refresh",
            "keys": ["ctrl", "r"],
            "window_title": browser["title"],
            "process_name": browser.get("process_name"),
        }
