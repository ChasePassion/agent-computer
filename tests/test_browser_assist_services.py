from __future__ import annotations

import asyncio

import pytest

from agent_computer.models.browser_assist import (
    BrowserAssistActRequest,
    BrowserAssistActResponse,
    BrowserAssistLocateRequest,
    BrowserAssistLocateResponse,
    BrowserAssistObserveRequest,
)
from agent_computer.retry import RetryDisposition, RetryDispositionError
from agent_computer.services.browser_assist_connection_manager import BrowserAssistConnectionManager
from agent_computer.services.browser_assist_service import BrowserAssistService
from agent_computer.services.session_service import SessionService


class StubWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed: tuple[int, str] | None = None

    async def accept(self) -> None:
        return None

    async def close(self, code: int, reason: str) -> None:
        self.closed = (code, reason)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def build_context(*, tab_session_id: str = "tab-1", document_epoch: int = 3) -> dict:
    return {
        "tabSessionId": tab_session_id,
        "tabId": 123,
        "frameId": 0,
        "windowId": 456,
        "url": "https://example.test/page",
        "title": "Example Page",
        "documentEpoch": document_epoch,
    }


def build_locate_result(*, tab_session_id: str = "tab-1", document_epoch: int = 3) -> dict:
    context = build_context(tab_session_id=tab_session_id, document_epoch=document_epoch)
    return {
        "context": context,
        "page": {
            "url": context["url"],
            "title": context["title"],
            "scrollX": 0,
            "scrollY": 0,
            "viewportWidth": 1280,
            "viewportHeight": 720,
            "devicePixelRatio": 1,
            "documentEpoch": document_epoch,
        },
        "viewport": {
            "offsetLeft": 0,
            "offsetTop": 0,
            "scale": 1,
        },
        "browser": {
            "contentLeftOnScreen": 10,
            "contentTopOnScreen": 20,
            "raw": {
                "screenX": 0,
                "screenY": 0,
                "outerWidth": 1280,
                "outerHeight": 720,
                "innerWidth": 1280,
                "innerHeight": 720,
                "inferredLeftInset": 0,
                "inferredTopInset": 0,
            },
        },
        "flags": {
            "bodyContainsSecurityText": False,
            "isSecurityPage": False,
        },
        "matchCount": 1,
        "matches": [
            {
                "id": "candidate-1",
                "text": "Like",
                "textRaw": "Like",
                "normalizedText": "Like",
                "role": "button",
                "tagName": "BUTTON",
                "selectorHint": "button.like",
                "rect": {
                    "left": 100,
                    "top": 200,
                    "width": 80,
                    "height": 32,
                    "right": 180,
                    "bottom": 232,
                },
                "visibleRect": {
                    "left": 100,
                    "top": 200,
                    "width": 80,
                    "height": 32,
                    "right": 180,
                    "bottom": 232,
                },
                "nodeRef": {
                    "nodeId": "node-3-1",
                    "tabSessionId": tab_session_id,
                    "frameId": 0,
                    "documentEpoch": document_epoch,
                    "selectorHint": "button.like",
                    "locatorRecipe": {
                        "role": "button",
                        "text": "Like",
                        "selectorHint": "button.like",
                        "ancestorHints": [],
                        "indexHint": 0,
                    },
                },
                "clickablePoint": {"x": 120, "y": 216},
                "actionability": {
                    "sameSession": True,
                    "attached": True,
                    "visible": True,
                    "notOccluded": True,
                    "enabled": True,
                    "editable": False,
                    "stable": True,
                },
                "visibleRatio": 1.0,
                "fullyVisible": True,
                "occluded": False,
                "selected": False,
                "actionabilityScore": 1.0,
                "score": 22.0,
            }
        ],
    }


def build_observe_result(*, tab_session_id: str = "tab-1", document_epoch: int = 3, exists: bool = True) -> dict:
    return {
        "context": build_context(tab_session_id=tab_session_id, document_epoch=document_epoch),
        "observation": {
            "nodeRef": {
                "nodeId": "node-3-1",
                "tabSessionId": tab_session_id,
                "frameId": 0,
                "documentEpoch": document_epoch,
                "selectorHint": "button.like",
                "locatorRecipe": {
                    "role": "button",
                    "text": "Like",
                    "selectorHint": "button.like",
                    "ancestorHints": [],
                    "indexHint": 0,
                },
            },
            "exists": exists,
            "text": "Like" if exists else None,
            "textRaw": "Like" if exists else None,
            "value": None,
            "selected": False if exists else None,
            "actionability": {
                "sameSession": True,
                "attached": exists,
                "visible": exists,
                "notOccluded": exists,
                "enabled": exists,
                "editable": False,
                "stable": exists,
            } if exists else None,
        },
    }


def build_act_result(*, tab_session_id: str = "tab-1", document_epoch: int = 3, verified: bool = True) -> dict:
    return {
        "context": build_context(tab_session_id=tab_session_id, document_epoch=document_epoch),
        "action": "click",
        "nodeRef": {
            "nodeId": "node-3-1",
            "tabSessionId": tab_session_id,
            "frameId": 0,
            "documentEpoch": document_epoch,
            "selectorHint": "button.like",
            "locatorRecipe": {
                "role": "button",
                "text": "Like",
                "selectorHint": "button.like",
                "ancestorHints": [],
                "indexHint": 0,
            },
        },
        "actionability": {
            "sameSession": True,
            "attached": True,
            "visible": True,
            "notOccluded": True,
            "enabled": True,
            "editable": False,
            "stable": True,
        },
        "verified": verified,
        "retryDisposition": "fail_fast" if verified else "retry_same_target",
        "failureReason": None if verified else "Verification timed out.",
        "observation": {
            "verificationSkipped": not verified,
        },
    }


def test_connection_manager_injects_tab_session_into_generic_requests() -> None:
    async def scenario() -> None:
        session = SessionService()
        manager = BrowserAssistConnectionManager(session)
        websocket = StubWebSocket()

        await manager.accept(websocket)
        await manager.handle_message(
            {
                "type": "hello",
                "payload": {
                    "extensionVersion": "1.0.0",
                    "browserName": "chromium",
                    "browserVersion": "test",
                    "activeSession": build_context(),
                },
            }
        )

        request_task = asyncio.create_task(manager.request_act({"action": "navigate", "url": "https://example.test/next"}))
        await asyncio.sleep(0)

        sent_message = websocket.sent[-1]
        assert sent_message["type"] == "act"
        assert sent_message["payload"]["tabSessionId"] == "tab-1"

        await manager.handle_message(
            {
                "type": "act-result",
                "requestId": sent_message["requestId"],
                "payload": build_act_result(),
            }
        )
        result = await request_task

        assert result["context"]["tabSessionId"] == "tab-1"
        snapshot = manager.snapshot()
        assert snapshot["currentTabSessionId"] == "tab-1"
        assert snapshot["preferredTabSessionId"] == "tab-1"

    asyncio.run(scenario())


def test_connection_manager_retains_current_document_identity() -> None:
    async def scenario() -> None:
        manager = BrowserAssistConnectionManager(SessionService())
        websocket = StubWebSocket()
        context = build_context()
        context.update({"documentId": "document-current", "pageNonce": "nonce-current"})

        await manager.accept(websocket)
        await manager.handle_message({"type": "hello", "payload": {"activeSession": context}})

        snapshot = manager.snapshot()
        assert snapshot["currentDocumentId"] == "document-current"
        assert snapshot["currentPageNonce"] == "nonce-current"

    asyncio.run(scenario())


def test_connection_manager_extends_act_timeout_for_verify_window() -> None:
    manager = BrowserAssistConnectionManager(SessionService())

    assert manager._resolve_act_timeout_sec({"action": "click"}, default=5.0) == 5.0
    assert manager._resolve_act_timeout_sec(
        {"action": "click", "verify": {"kind": "element_appeared", "timeoutMs": 5000}},
        default=5.0,
    ) == 7.0


def test_connection_manager_does_not_retry_an_ambiguous_action_timeout() -> None:
    async def scenario() -> None:
        manager = BrowserAssistConnectionManager(SessionService())
        websocket = StubWebSocket()
        await manager.accept(websocket)

        with pytest.raises(RetryDispositionError) as exc_info:
            await manager.request(
                "act",
                {"action": "click", "nodeRef": {"nodeId": "node-1"}},
                timeout_sec=0.001,
            )

        assert exc_info.value.retry_disposition == RetryDisposition.FAIL_FAST
        assert exc_info.value.details == {
            "requestType": "act",
            "outcome": "unknown",
            "actionMayHaveExecuted": True,
        }

    asyncio.run(scenario())


class StubManager:
    def __init__(self, *, locate_payload=None, observe_payload=None, act_payload=None) -> None:
        self.locate_payload = locate_payload
        self.observe_payload = observe_payload
        self.act_payload = act_payload

    def token(self) -> str:
        return "TOKEN123"

    def snapshot(self) -> dict:
        return {
            "connected": True,
            "token": "TOKEN123",
            "protocolVersion": 1,
        }

    async def request_locate(self, _payload: dict, *, timeout_sec: float = 3.0) -> dict:
        return self.locate_payload

    async def request_observe(self, _payload: dict, *, timeout_sec: float = 3.0) -> dict:
        return self.observe_payload

    async def request_act(self, _payload: dict, *, timeout_sec: float = 5.0) -> dict:
        return self.act_payload


def test_browser_assist_locate_returns_direct_session_first_payload() -> None:
    service = BrowserAssistService(SessionService(), StubManager(locate_payload=build_locate_result()))
    request = BrowserAssistLocateRequest.model_validate({"query": {"text": "Like", "role": "button"}})

    response = asyncio.run(service.locate(request))

    assert response.context is not None
    assert response.context.tabSessionId == "tab-1"
    assert response.matches[0].nodeRef is not None
    assert response.matches[0].nodeRef.tabSessionId == "tab-1"


def test_browser_assist_observe_rejects_stale_document_epoch() -> None:
    service = BrowserAssistService(SessionService(), StubManager(observe_payload=build_observe_result(document_epoch=7)))
    request = BrowserAssistObserveRequest.model_validate(
        {
            "nodeRef": {
                "nodeId": "node-3-1",
                "tabSessionId": "tab-1",
                "frameId": 0,
                "documentEpoch": 6,
                "selectorHint": "button.like",
                "locatorRecipe": {
                    "role": "button",
                    "text": "Like",
                    "selectorHint": "button.like",
                    "ancestorHints": [],
                    "indexHint": 0,
                },
            }
        }
    )

    with pytest.raises(RetryDispositionError) as exc_info:
        asyncio.run(service.observe(request))

    assert exc_info.value.retry_disposition == RetryDisposition.REACQUIRE_TARGET


def test_browser_assist_act_round_trips_node_ref_based_action() -> None:
    service = BrowserAssistService(SessionService(), StubManager(act_payload=build_act_result()))
    request = BrowserAssistActRequest.model_validate(
        {
            "action": "click",
            "nodeRef": {
                "nodeId": "node-3-1",
                "tabSessionId": "tab-1",
                "frameId": 0,
                "documentEpoch": 3,
                "selectorHint": "button.like",
                "locatorRecipe": {
                    "role": "button",
                    "text": "Like",
                    "selectorHint": "button.like",
                    "ancestorHints": [],
                    "indexHint": 0,
                },
            },
        }
    )

    response = asyncio.run(service.act(request))

    assert response.verified is False
    assert response.verificationStatus == "not_requested"
    assert response.nodeRef is not None
    assert response.nodeRef.tabSessionId == "tab-1"
    assert response.retryDisposition == RetryDisposition.FAIL_FAST


def test_browser_assist_act_requires_requested_verification_to_report_passed() -> None:
    payload = build_act_result()
    payload["verificationStatus"] = "passed"
    service = BrowserAssistService(SessionService(), StubManager(act_payload=payload))
    request = BrowserAssistActRequest.model_validate(
        {
            "action": "click",
            "nodeRef": {
                "nodeId": "node-3-1",
                "tabSessionId": "tab-1",
                "frameId": 0,
                "documentEpoch": 3,
            },
            "verify": {"kind": "text_changed"},
        }
    )

    response = asyncio.run(service.act(request))

    assert response.verified is True
    assert response.verificationStatus == "passed"


def test_locate_response_accepts_standard_aria_roles_and_document_identity() -> None:
    payload = build_locate_result()
    payload["context"]["documentId"] = "document-uuid-1"
    payload["context"]["pageNonce"] = "nonce-uuid-1"
    payload["page"]["documentId"] = "document-uuid-1"
    payload["page"]["pageNonce"] = "nonce-uuid-1"
    payload["matches"][0]["role"] = "combobox"
    payload["matches"][0]["nodeRef"]["documentId"] = "document-uuid-1"
    payload["matches"][0]["nodeRef"]["pageNonce"] = "nonce-uuid-1"
    payload["matches"][0]["nodeRef"]["locatorRecipe"]["role"] = "combobox"

    response = BrowserAssistLocateResponse.model_validate(payload)

    assert response.context is not None
    assert response.context.documentId == "document-uuid-1"
    assert response.context.pageNonce == "nonce-uuid-1"
    assert response.matches[0].role == "combobox"
    assert response.matches[0].nodeRef is not None
    assert response.matches[0].nodeRef.documentId == "document-uuid-1"
    assert response.matches[0].nodeRef.pageNonce == "nonce-uuid-1"


def test_browser_assist_observe_rejects_stale_document_id_even_when_epoch_matches() -> None:
    payload = build_observe_result(document_epoch=3)
    payload["context"].update({"documentId": "document-new", "pageNonce": "nonce-new"})
    payload["observation"]["nodeRef"].update({"documentId": "document-new", "pageNonce": "nonce-new"})
    service = BrowserAssistService(SessionService(), StubManager(observe_payload=payload))
    request = BrowserAssistObserveRequest.model_validate(
        {
            "nodeRef": {
                "nodeId": "dom:nonce-old:3:1",
                "tabSessionId": "tab-1",
                "frameId": 0,
                "documentEpoch": 3,
                "documentId": "document-old",
                "pageNonce": "nonce-old",
            }
        }
    )

    with pytest.raises(RetryDispositionError) as exc_info:
        asyncio.run(service.observe(request))

    assert exc_info.value.retry_disposition == RetryDisposition.REACQUIRE_TARGET


def test_browser_assist_observe_rejects_a_response_without_document_context() -> None:
    payload = build_observe_result(document_epoch=3)
    payload["context"] = None
    service = BrowserAssistService(SessionService(), StubManager(observe_payload=payload))
    request = BrowserAssistObserveRequest.model_validate(
        {
            "nodeRef": {
                "nodeId": "dom:nonce-current:3:1",
                "tabSessionId": "tab-1",
                "frameId": 0,
                "documentEpoch": 3,
                "documentId": "document-current",
                "pageNonce": "nonce-current",
            }
        }
    )

    with pytest.raises(RetryDispositionError) as exc_info:
        asyncio.run(service.observe(request))

    assert exc_info.value.retry_disposition == RetryDisposition.CONTEXT_LOST


def test_verification_skipped_is_not_reported_as_verified() -> None:
    payload = build_act_result(verified=True)
    payload["observation"] = {"verificationSkipped": True}

    response = BrowserAssistActResponse.model_validate(payload)

    assert response.verificationStatus == "not_requested"
    assert response.verified is False
