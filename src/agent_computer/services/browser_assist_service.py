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
            actual_context=response.context,
        )
        if response.observation.nodeRef is not None:
            self._validate_context(
                requested_tab_session_id=request.nodeRef.tabSessionId,
                requested_document_epoch=request.nodeRef.documentEpoch,
                actual_context=response.context,
                actual_node_document_epoch=response.observation.nodeRef.documentEpoch,
            )
        return response

    async def act(self, request: BrowserAssistActRequest) -> BrowserAssistActResponse:
        response = BrowserAssistActResponse.model_validate(
            await self.connection_manager.request_act(request.model_dump(mode="json"))
        )
        requested_tab_session_id = request.tabSessionId or (None if request.nodeRef is None else request.nodeRef.tabSessionId)
        requested_document_epoch = None if request.nodeRef is None or response.nodeRef is None else request.nodeRef.documentEpoch
        self._validate_context(
            requested_tab_session_id=requested_tab_session_id,
            requested_document_epoch=requested_document_epoch,
            actual_context=response.context,
            actual_node_document_epoch=None if response.nodeRef is None else response.nodeRef.documentEpoch,
        )
        return response

    def _validate_context(
        self,
        *,
        requested_tab_session_id: str | None,
        requested_document_epoch: int | None,
        actual_context,
        actual_node_document_epoch: int | None = None,
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

        if requested_document_epoch is None or actual_context is None:
            return

        actual_document_epoch = actual_node_document_epoch if actual_node_document_epoch is not None else actual_context.documentEpoch
        if actual_document_epoch != requested_document_epoch:
            raise RetryDispositionError(
                "Browser Assist documentEpoch no longer matches the active request context.",
                retry_disposition=RetryDisposition.REACQUIRE_TARGET,
                details={
                    "requestedDocumentEpoch": requested_document_epoch,
                    "actualDocumentEpoch": actual_document_epoch,
                },
            )
