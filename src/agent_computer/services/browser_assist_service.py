from __future__ import annotations

from agent_computer.models.browser_assist import (
    BrowserAssistActRequest,
    BrowserAssistActResponse,
    BrowserAssistLocateRequest,
    BrowserAssistLocateResponse,
    BrowserAssistObserveRequest,
    BrowserAssistObserveResponse,
    BrowserAssistStatusResponse,
)
from agent_computer.retry import RetryDisposition, RetryDispositionError
from agent_computer.services.browser_assist_connection_manager import BrowserAssistConnectionManager
from agent_computer.services.session_service import SessionService


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
        response = BrowserAssistLocateResponse.model_validate(
            await self.connection_manager.request_locate(request.model_dump(mode="json"))
        )
        self._validate_context(
            requested_tab_session_id=request.tabSessionId,
            requested_document_epoch=request.documentEpoch,
            requested_document_id=request.documentId,
            requested_page_nonce=request.pageNonce,
            actual_context=response.context,
        )
        return response

    async def observe(self, request: BrowserAssistObserveRequest) -> BrowserAssistObserveResponse:
        response = BrowserAssistObserveResponse.model_validate(
            await self.connection_manager.request_observe(request.model_dump(mode="json"))
        )
        self._validate_context(
            requested_tab_session_id=request.nodeRef.tabSessionId,
            requested_document_epoch=request.nodeRef.documentEpoch,
            requested_document_id=request.nodeRef.documentId,
            requested_page_nonce=request.nodeRef.pageNonce,
            actual_context=response.context,
        )
        if response.observation.nodeRef is not None:
            self._validate_context(
                requested_tab_session_id=request.nodeRef.tabSessionId,
                requested_document_epoch=request.nodeRef.documentEpoch,
                requested_document_id=request.nodeRef.documentId,
                requested_page_nonce=request.nodeRef.pageNonce,
                actual_context=response.context,
                actual_node_document_epoch=response.observation.nodeRef.documentEpoch,
                actual_node_document_id=response.observation.nodeRef.documentId,
                actual_node_page_nonce=response.observation.nodeRef.pageNonce,
            )
        return response

    async def act(self, request: BrowserAssistActRequest) -> BrowserAssistActResponse:
        response = BrowserAssistActResponse.model_validate(
            await self.connection_manager.request_act(request.model_dump(mode="json"))
        )
        if request.verify is None:
            response = response.model_copy(
                update={"verified": False, "verificationStatus": "not_requested"}
            )
        elif response.verificationStatus == "not_requested":
            response = response.model_copy(
                update={
                    "verified": False,
                    "failureReason": response.failureReason
                    or "The extension did not run the requested verification.",
                    "retryDisposition": RetryDisposition.RETRY_SAME_TARGET,
                }
            )
        requested_tab_session_id = request.tabSessionId or (None if request.nodeRef is None else request.nodeRef.tabSessionId)
        requested_document_epoch = None if request.nodeRef is None else request.nodeRef.documentEpoch
        self._validate_context(
            requested_tab_session_id=requested_tab_session_id,
            requested_document_epoch=requested_document_epoch,
            requested_document_id=None if request.nodeRef is None else request.nodeRef.documentId,
            requested_page_nonce=None if request.nodeRef is None else request.nodeRef.pageNonce,
            actual_context=response.context,
            actual_node_document_epoch=None if response.nodeRef is None else response.nodeRef.documentEpoch,
            actual_node_document_id=None if response.nodeRef is None else response.nodeRef.documentId,
            actual_node_page_nonce=None if response.nodeRef is None else response.nodeRef.pageNonce,
        )
        return response

    def _validate_context(
        self,
        *,
        requested_tab_session_id: str | None,
        requested_document_epoch: int | None,
        requested_document_id: str | None,
        requested_page_nonce: str | None,
        actual_context,
        actual_node_document_epoch: int | None = None,
        actual_node_document_id: str | None = None,
        actual_node_page_nonce: str | None = None,
    ) -> None:
        if requested_tab_session_id and actual_context is not None and actual_context.tabSessionId != requested_tab_session_id:
            raise RetryDispositionError(
                "Browser Assist returned a different tab session than the active request context.",
                retry_disposition=RetryDisposition.CONTEXT_LOST,
                details={
                    "requestedTabSessionId": requested_tab_session_id,
                    "actualTabSessionId": actual_context.tabSessionId,
                },
            )

        if actual_context is None:
            raise RetryDispositionError(
                "Browser Assist response did not include the document context required to validate its target.",
                retry_disposition=RetryDisposition.CONTEXT_LOST,
                details={
                    "requestedTabSessionId": requested_tab_session_id,
                    "requestedDocumentId": requested_document_id,
                },
            )

        actual_document_epoch = actual_node_document_epoch if actual_node_document_epoch is not None else actual_context.documentEpoch
        actual_document_id = actual_node_document_id or actual_context.documentId
        actual_page_nonce = actual_node_page_nonce or actual_context.pageNonce
        identity_mismatch = (
            (requested_document_id is not None and actual_document_id != requested_document_id)
            or (requested_page_nonce is not None and actual_page_nonce != requested_page_nonce)
        )
        epoch_mismatch = requested_document_epoch is not None and actual_document_epoch != requested_document_epoch
        if identity_mismatch or epoch_mismatch:
            raise RetryDispositionError(
                "Browser Assist document identity no longer matches the active request context.",
                retry_disposition=RetryDisposition.REACQUIRE_TARGET,
                details={
                    "requestedDocumentEpoch": requested_document_epoch,
                    "actualDocumentEpoch": actual_document_epoch,
                    "requestedDocumentId": requested_document_id,
                    "actualDocumentId": actual_document_id,
                },
            )
