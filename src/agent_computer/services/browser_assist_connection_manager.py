from __future__ import annotations

import asyncio
import secrets
import string
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from agent_computer.runtime import browser_assist_config_path, read_json, write_json
from agent_computer.services.session_service import SessionService

PROTOCOL_VERSION = 1


class BrowserAssistConnectionManager:
    def __init__(self, session: SessionService) -> None:
        self.session = session
        self._lock = asyncio.Lock()
        self._websocket: WebSocket | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._token = self._ensure_token()
        self._last_seen_at: str | None = None
        self._last_error: str | None = None
        self._extension_info: dict[str, Any] = {}
        self._last_page: dict[str, Any] = {}
        self.session.set_browser_assist_token(self._token)

    def token(self) -> str:
        return self._token

    def snapshot(self) -> dict[str, Any]:
        connected = self._websocket is not None
        return {
            "connected": connected,
            "token": self._token,
            "protocolVersion": PROTOCOL_VERSION,
            "lastSeenAt": self._last_seen_at,
            "lastError": self._last_error,
            "extensionVersion": self._extension_info.get("extensionVersion"),
            "browserName": self._extension_info.get("browserName"),
            "browserVersion": self._extension_info.get("browserVersion"),
            "lastPageUrl": self._last_page.get("url"),
            "lastPageTitle": self._last_page.get("title"),
        }

    async def accept(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            existing = self._websocket
            self._websocket = websocket
            self._last_error = None
            self._touch()
            self._sync_session_locked()

        if existing is not None and existing is not websocket:
            await existing.close(code=1012, reason="Replaced by newer Browser Assist connection.")

    async def disconnect(self, websocket: WebSocket, *, reason: str | None = None) -> None:
        async with self._lock:
            if self._websocket is websocket:
                self._websocket = None
            self._last_error = reason
            pending = list(self._pending.values())
            self._pending.clear()
            self._sync_session_locked()

        for future in pending:
            if not future.done():
                future.set_exception(RuntimeError(reason or "Browser Assist extension disconnected."))

    async def handle_message(self, message: dict[str, Any]) -> None:
        message_type = str(message.get("type") or "").strip()
        payload = message.get("payload")
        future: asyncio.Future[dict[str, Any]] | None = None
        error_message: str | None = None

        async with self._lock:
            self._touch()
            if message_type == "hello" and isinstance(payload, dict):
                self._extension_info = dict(payload)
                self._sync_session_locked()
                return

            if message_type == "keepalive":
                self._sync_session_locked()
                return

            if message_type == "locate-result" and isinstance(payload, dict):
                request_id = str(message.get("requestId") or "").strip()
                future = self._pending.pop(request_id, None)
                page = payload.get("page")
                if isinstance(page, dict):
                    self._last_page = dict(page)
                self._sync_session_locked()
            elif message_type == "error":
                request_id = str(message.get("requestId") or "").strip()
                future = self._pending.pop(request_id, None)
                error_message = str(message.get("message") or "Browser Assist extension returned an error.")
                self._last_error = error_message
                self._sync_session_locked()
            else:
                return

        if message_type == "locate-result":
            if future is not None and not future.done():
                future.set_result(dict(payload))
            return

        if message_type == "error":
            if future is not None and not future.done():
                future.set_exception(RuntimeError(error_message or "Browser Assist extension returned an error."))

    async def request_locate(self, payload: dict[str, Any], *, timeout_sec: float = 3.0) -> dict[str, Any]:
        request_id = f"req-{uuid4().hex}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        async with self._lock:
            websocket = self._websocket
            if websocket is None:
                raise RuntimeError("Browser Assist extension is not connected.")
            self._pending[request_id] = future

        message = {
            "type": "locate",
            "requestId": request_id,
            "payload": payload,
        }

        try:
            await websocket.send_json(message)
        except Exception as exc:
            async with self._lock:
                self._pending.pop(request_id, None)
                self._last_error = str(exc)
                self._sync_session_locked()
            raise RuntimeError(f"Failed to send locate request to Browser Assist extension: {exc}") from exc

        try:
            return await asyncio.wait_for(future, timeout=timeout_sec)
        except asyncio.TimeoutError as exc:
            async with self._lock:
                self._pending.pop(request_id, None)
                self._last_error = f"Browser Assist locate request timed out after {timeout_sec:.1f}s."
                self._sync_session_locked()
            raise RuntimeError(self._last_error) from exc

    def _ensure_token(self) -> str:
        path = browser_assist_config_path()
        if path.exists():
            payload = read_json(path)
            token = str(payload.get("token") or "").strip()
            if token:
                return token

        alphabet = string.ascii_uppercase + string.digits
        token = "".join(secrets.choice(alphabet) for _ in range(12))
        write_json(
            path,
            {
                "token": token,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        return token

    def _touch(self) -> None:
        self._last_seen_at = datetime.now().astimezone().isoformat(timespec="seconds")

    def _sync_session_locked(self) -> None:
        self.session.set_browser_assist_connected(self._websocket is not None)
        self.session.set_browser_assist_last_keepalive_at(self._last_seen_at)
        self.session.set_browser_assist_last_page_url(self._last_page.get("url"))
        self.session.set_browser_assist_last_page_title(self._last_page.get("title"))
        self.session.set_browser_assist_last_error(self._last_error)
