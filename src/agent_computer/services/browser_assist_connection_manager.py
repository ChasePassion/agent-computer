from __future__ import annotations

import asyncio
import secrets
import string
import time
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import WebSocket

from agent_computer.retry import RetryDisposition, RetryDispositionError, classify_browser_assist_error, normalize_retry_disposition
from agent_computer.runtime import browser_assist_config_path, read_json, write_json
from agent_computer.services.session_service import SessionService
from agent_computer.structured_logging import get_event_logger, log_event

PROTOCOL_VERSION = 1
BrowserAssistRequestType = Literal["locate", "observe", "act"]
BrowserAssistResultType = Literal["locate-result", "observe-result", "act-result"]
LOGGER = get_event_logger("browser-assist")


class BrowserAssistConnectionManager:
    def __init__(self, session: SessionService, *, metrics: Any | None = None) -> None:
        self.session = session
        self._lock = asyncio.Lock()
        self._websocket: WebSocket | None = None
        self._pending: dict[str, tuple[asyncio.Future[dict[str, Any]], BrowserAssistRequestType, dict[str, Any]]] = {}
        self._token = self._ensure_token()
        self._last_seen_at: str | None = None
        self._last_error: str | None = None
        self._extension_info: dict[str, Any] = {}
        self._last_page: dict[str, Any] = {}
        self._tab_sessions: dict[str, dict[str, Any]] = {}
        self._current_tab_session_id: str | None = None
        self._preferred_tab_session_id: str | None = None
        self.metrics = metrics
        self.session.set_browser_assist_token(self._token)

    def token(self) -> str:
        return self._token

    def current_tab_session(self) -> dict[str, Any] | None:
        session_id = self._preferred_tab_session_id or self._current_tab_session_id
        if not session_id:
            return None
        session = self._tab_sessions.get(session_id)
        return None if session is None else dict(session)

    def snapshot(self) -> dict[str, Any]:
        connected = self._websocket is not None
        current_session = self.current_tab_session() or {}
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
            "currentTabSessionId": current_session.get("tabSessionId"),
            "preferredTabSessionId": self._preferred_tab_session_id,
            "currentTabId": current_session.get("tabId"),
            "currentFrameId": current_session.get("frameId"),
            "currentWindowId": current_session.get("windowId"),
            "currentDocumentEpoch": current_session.get("documentEpoch"),
            "currentDocumentId": current_session.get("documentId"),
            "currentPageNonce": current_session.get("pageNonce"),
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
            pending = [entry[0] for entry in self._pending.values()]
            self._pending.clear()
            self._tab_sessions.clear()
            self._current_tab_session_id = None
            self._preferred_tab_session_id = None
            self._sync_session_locked()

        for future in pending:
            if not future.done():
                future.set_exception(
                    RetryDispositionError(
                        reason or "Browser Assist extension disconnected.",
                        retry_disposition=RetryDisposition.CONTEXT_LOST,
                    )
                )

    async def handle_message(self, message: dict[str, Any]) -> None:
        message_type = str(message.get("type") or "").strip()
        payload = message.get("payload")
        future: asyncio.Future[dict[str, Any]] | None = None
        request_type: BrowserAssistRequestType | None = None
        request_payload: dict[str, Any] = {}
        error_message: str | None = None
        retry_disposition = RetryDisposition.FAIL_FAST

        async with self._lock:
            self._touch()
            if message_type == "hello" and isinstance(payload, dict):
                self._extension_info = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"activeSession", "session"}
                }
                self._update_tab_session_locked(payload.get("activeSession") or payload.get("session"))
                self._sync_session_locked()
                return

            if message_type == "session-state" and isinstance(payload, dict):
                self._update_tab_session_locked(payload.get("session") or payload.get("activeSession") or payload)
                self._sync_session_locked()
                return

            if message_type == "keepalive":
                if isinstance(payload, dict):
                    self._update_tab_session_locked(payload.get("session") or payload.get("activeSession"))
                self._sync_session_locked()
                return

            if message_type in {"locate-result", "observe-result", "act-result"} and isinstance(payload, dict):
                request_id = str(message.get("requestId") or "").strip()
                pending = self._pending.pop(request_id, None)
                if pending is not None:
                    future, request_type, request_payload = pending
                page = payload.get("page")
                if isinstance(page, dict):
                    self._last_page = dict(page)
                context = self._update_tab_session_locked(payload.get("context"))
                self._promote_preferred_session_locked(context=context, request_payload=request_payload)
                self._sync_session_locked()
            elif message_type == "error":
                request_id = str(message.get("requestId") or "").strip()
                pending = self._pending.pop(request_id, None)
                if pending is not None:
                    future, request_type, _request_payload = pending
                error_payload = payload if isinstance(payload, dict) else {}
                error_message = str(error_payload.get("message") or message.get("message") or "Browser Assist extension returned an error.")
                retry_disposition = normalize_retry_disposition(
                    error_payload.get("retryDisposition"),
                    classify_browser_assist_error(error_message),
                )
                self._last_error = error_message
                if retry_disposition == RetryDisposition.CONTEXT_LOST:
                    self._preferred_tab_session_id = None
                self._sync_session_locked()
            else:
                return

        if message_type in {"locate-result", "observe-result", "act-result"}:
            if future is not None and not future.done():
                future.set_result(dict(payload))
            return

        if message_type == "error":
            if future is not None and not future.done():
                future.set_exception(
                    RetryDispositionError(
                        error_message or "Browser Assist extension returned an error.",
                        retry_disposition=retry_disposition,
                        details={"requestType": request_type},
                    )
                )

    async def request(
        self,
        request_type: BrowserAssistRequestType,
        payload: dict[str, Any],
        *,
        timeout_sec: float = 3.0,
    ) -> dict[str, Any]:
        started_ns = time.monotonic_ns()
        request_id = f"req-{uuid4().hex}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        async with self._lock:
            websocket = self._websocket
            if websocket is None:
                raise RetryDispositionError(
                    "Browser Assist extension is not connected.",
                    retry_disposition=RetryDisposition.CONTEXT_LOST,
                )
            request_payload = self._prepare_request_payload_locked(payload)
            self._pending[request_id] = (future, request_type, request_payload)

        message = {
            "type": request_type,
            "requestId": request_id,
            "payload": request_payload,
        }

        try:
            await websocket.send_json(message)
        except Exception as exc:
            async with self._lock:
                self._pending.pop(request_id, None)
                self._last_error = str(exc)
                self._preferred_tab_session_id = None
                self._sync_session_locked()
            self._record_request_metric(request_type, started_ns, "failed")
            log_event(
                LOGGER,
                event="browser_assist.send_failed",
                message="Browser Assist request could not be sent",
                outcome="failed",
                request_type=request_type,
            )
            raise RetryDispositionError(
                f"Failed to send Browser Assist {request_type} request: {exc}",
                retry_disposition=RetryDisposition.CONTEXT_LOST,
            ) from exc

        try:
            result = await asyncio.wait_for(future, timeout=timeout_sec)
        except asyncio.TimeoutError as exc:
            action_outcome_unknown = request_type == "act"
            async with self._lock:
                self._pending.pop(request_id, None)
                self._last_error = f"Browser Assist {request_type} request timed out after {timeout_sec:.1f}s."
                if action_outcome_unknown:
                    self._last_error += " The action may have executed; do not retry it automatically."
                self._sync_session_locked()
            self._record_request_metric(request_type, started_ns, "timeout")
            log_event(
                LOGGER,
                event="browser_assist.request_timeout",
                message="Browser Assist request timed out",
                outcome="timeout",
                request_type=request_type,
                timeout_ms=round(timeout_sec * 1000, 3),
            )
            raise RetryDispositionError(
                self._last_error,
                retry_disposition=(
                    RetryDisposition.FAIL_FAST
                    if action_outcome_unknown
                    else RetryDisposition.RETRY_SAME_TARGET
                ),
                details=(
                    {
                        "requestType": request_type,
                        "outcome": "unknown",
                        "actionMayHaveExecuted": True,
                    }
                    if action_outcome_unknown
                    else {"requestType": request_type}
                ),
            ) from exc
        except Exception:
            self._record_request_metric(request_type, started_ns, "failed")
            raise
        self._record_request_metric(request_type, started_ns, "success")
        return result

    def _record_request_metric(self, request_type: str, started_ns: int, outcome: str) -> None:
        if self.metrics is None or not hasattr(self.metrics, "record"):
            return
        duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
        self.metrics.record(
            f"browser_assist.{request_type}",
            duration_ms=duration_ms,
            outcome=outcome,
        )

    async def request_locate(self, payload: dict[str, Any], *, timeout_sec: float = 6.0) -> dict[str, Any]:
        return await self.request("locate", payload, timeout_sec=timeout_sec)

    async def request_observe(self, payload: dict[str, Any], *, timeout_sec: float = 3.0) -> dict[str, Any]:
        return await self.request("observe", payload, timeout_sec=timeout_sec)

    async def request_act(self, payload: dict[str, Any], *, timeout_sec: float = 5.0) -> dict[str, Any]:
        return await self.request("act", payload, timeout_sec=self._resolve_act_timeout_sec(payload, default=timeout_sec))

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

    def _prepare_request_payload_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = dict(payload)
        node_ref = request_payload.get("nodeRef")
        if isinstance(node_ref, dict):
            node_ref = dict(node_ref)
        else:
            node_ref = None

        tab_session_id = str(request_payload.get("tabSessionId") or "").strip()
        if not tab_session_id and isinstance(node_ref, dict):
            tab_session_id = str(node_ref.get("tabSessionId") or "").strip()

        if not tab_session_id:
            tab_session_id = self._preferred_tab_session_id or self._current_tab_session_id or ""

        if tab_session_id:
            request_payload["tabSessionId"] = tab_session_id
            current_session = self._tab_sessions.get(tab_session_id) or {}
            for key in ("documentEpoch", "documentId", "pageNonce"):
                if request_payload.get(key) is None and current_session.get(key) is not None:
                    request_payload[key] = current_session[key]
            if isinstance(node_ref, dict):
                node_ref["tabSessionId"] = tab_session_id
                for key in ("documentEpoch", "documentId", "pageNonce"):
                    if node_ref.get(key) is None and current_session.get(key) is not None:
                        node_ref[key] = current_session[key]
                request_payload["nodeRef"] = node_ref

        return request_payload

    @staticmethod
    def _resolve_act_timeout_sec(payload: dict[str, Any], *, default: float) -> float:
        verify = payload.get("verify")
        if not isinstance(verify, dict):
            return default

        timeout_ms = verify.get("timeoutMs")
        try:
            verify_timeout_sec = max(0.0, float(timeout_ms) / 1000.0)
        except (TypeError, ValueError):
            return default

        # Give the extension enough time to execute the action, wait for postconditions,
        # and ship the result back across the websocket boundary.
        return max(default, verify_timeout_sec + 2.0)

    def _promote_preferred_session_locked(self, *, context: dict[str, Any] | None, request_payload: dict[str, Any]) -> None:
        context_session_id = str((context or {}).get("tabSessionId") or "").strip()
        requested_session_id = str(request_payload.get("tabSessionId") or "").strip()
        if context_session_id and (not requested_session_id or requested_session_id == context_session_id):
            self._preferred_tab_session_id = context_session_id

    def _update_tab_session_locked(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        tab_session_id = str(payload.get("tabSessionId") or "").strip()
        tab_id = self._coerce_int(payload.get("tabId"))
        if not tab_session_id or tab_id is None:
            return None

        session_payload = {
            "tabSessionId": tab_session_id,
            "tabId": tab_id,
            "frameId": self._coerce_int(payload.get("frameId")),
            "windowId": self._coerce_int(payload.get("windowId")),
            "url": self._coerce_str(payload.get("url")),
            "title": self._coerce_str(payload.get("title")),
            "documentEpoch": self._coerce_int(payload.get("documentEpoch"), default=0) or 0,
            "documentId": self._coerce_str(payload.get("documentId")),
            "pageNonce": self._coerce_str(payload.get("pageNonce")),
        }
        self._tab_sessions[tab_session_id] = session_payload
        self._current_tab_session_id = tab_session_id

        if session_payload["url"]:
            self._last_page = {
                "url": session_payload["url"],
                "title": session_payload["title"],
            }

        return session_payload

    @staticmethod
    def _coerce_int(value: Any, *, default: int | None = None) -> int | None:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _sync_session_locked(self) -> None:
        current_session = self.current_tab_session() or {}
        self.session.set_browser_assist_connected(self._websocket is not None)
        self.session.set_browser_assist_last_keepalive_at(self._last_seen_at)
        self.session.set_browser_assist_last_page_url(self._last_page.get("url"))
        self.session.set_browser_assist_last_page_title(self._last_page.get("title"))
        self.session.set_browser_assist_last_error(self._last_error)
        self.session.set_browser_assist_current_tab_session_id(current_session.get("tabSessionId"))
        self.session.set_browser_assist_preferred_tab_session_id(self._preferred_tab_session_id)
        self.session.set_browser_assist_current_document_epoch(current_session.get("documentEpoch"))
