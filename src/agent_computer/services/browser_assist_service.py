from __future__ import annotations

from typing import Any

from agent_computer.actions import browser_current_url as read_browser_current_url
from agent_computer.models.browser_assist import (
    BrowserAssistLocateRequest,
    BrowserAssistLocateResponse,
    BrowserAssistMappedCandidate,
    BrowserAssistMappedResult,
    BrowserAssistRawResult,
    BrowserAssistScreenPoint,
    BrowserAssistStatusResponse,
)
from agent_computer.services.browser_assist_connection_manager import BrowserAssistConnectionManager
from agent_computer.services.session_service import SessionService
from agent_computer.windowing import require_foreground_browser_window


class BrowserAssistService:
    def __init__(
        self,
        session: SessionService,
        connection_manager: BrowserAssistConnectionManager | None = None,
    ) -> None:
        self.session = session
        self.connection_manager = connection_manager or BrowserAssistConnectionManager(session)

    def token(self) -> str:
        return self.connection_manager.token()

    def status(self) -> BrowserAssistStatusResponse:
        return BrowserAssistStatusResponse.model_validate(self.connection_manager.snapshot())

    async def locate(self, request: BrowserAssistLocateRequest) -> BrowserAssistLocateResponse:
        foreground_window = require_foreground_browser_window()
        current_url = read_browser_current_url()
        raw_payload = await self.connection_manager.request_locate(request.model_dump(mode="json"))
        raw = BrowserAssistRawResult.model_validate(raw_payload)

        self._validate_page_context(
            raw_page=raw.page.model_dump(mode="json"),
            foreground_window=foreground_window,
            current_url=current_url,
        )

        mapped = BrowserAssistMappedResult(
            screenCandidates=[
                self._map_candidate(raw, match, index)
                for index, match in enumerate(raw.matches)
            ]
        )
        return BrowserAssistLocateResponse(raw=raw, mapped=mapped)

    def _validate_page_context(
        self,
        *,
        raw_page: dict[str, Any],
        foreground_window: dict[str, Any],
        current_url: str,
    ) -> None:
        page_url = str(raw_page.get("url") or "").strip()
        page_title = str(raw_page.get("title") or "").strip()
        window_title = str(foreground_window.get("title") or "").strip()

        if page_url and current_url != page_url:
            raise RuntimeError(
                "Browser Assist page URL does not match the current foreground browser URL: "
                f"plugin={page_url!r}, browser={current_url!r}"
            )

        if page_title and page_title not in window_title:
            raise RuntimeError(
                "Browser Assist page title does not match the current foreground browser window: "
                f"plugin={page_title!r}, window={window_title!r}"
            )

    def _map_candidate(
        self,
        raw: BrowserAssistRawResult,
        match,
        index: int,
    ) -> BrowserAssistMappedCandidate:
        css_abs_x = raw.browser.contentLeftOnScreen + raw.viewport.offsetLeft + match.clickablePoint.x
        css_abs_y = raw.browser.contentTopOnScreen + raw.viewport.offsetTop + match.clickablePoint.y

        screen_x = round(css_abs_x * raw.page.devicePixelRatio)
        screen_y = round(css_abs_y * raw.page.devicePixelRatio)

        point = BrowserAssistScreenPoint(x=screen_x, y=screen_y)
        css_point = BrowserAssistScreenPoint(x=css_abs_x, y=css_abs_y)
        return BrowserAssistMappedCandidate(
            id=match.id or f"candidate-{index}",
            text=match.text,
            tagName=match.tagName,
            screenPoint=point,
            gridPoint=point,
            cssAbsolutePoint=css_point,
            rect=match.rect,
        )
