from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from agent_computer.retry import RetryDisposition

LocatorRole = str
BrowserAssistActionKind = Literal["click", "type", "navigate"]
BrowserAssistVerificationStatus = Literal["passed", "failed", "not_requested"]
BrowserAssistVerifyKind = Literal[
    "text_changed",
    "url_changed",
    "dialog_appeared",
    "selection_changed",
    "element_appeared",
    "element_disappeared",
]
BrowserAssistMessageType = Literal[
    "hello",
    "keepalive",
    "session-state",
    "locate",
    "locate-result",
    "observe",
    "observe-result",
    "act",
    "act-result",
    "error",
]


class BrowserAssistQuery(BaseModel):
    text: str | None = None
    role: LocatorRole = "any"
    hint: str | None = None

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        normalized = str(value or "any").strip().lower()
        return normalized or "any"


class BrowserAssistOptions(BaseModel):
    visibleOnly: bool = True
    interactiveOnly: bool = True
    maxCandidates: int = Field(default=5, ge=1, le=20)


class BrowserAssistLocateRequest(BaseModel):
    query: BrowserAssistQuery
    options: BrowserAssistOptions = Field(default_factory=BrowserAssistOptions)
    tabSessionId: str | None = None
    documentEpoch: int | None = Field(default=None, ge=0)
    documentId: str | None = None
    pageNonce: str | None = None


class BrowserTabSession(BaseModel):
    tabSessionId: str
    tabId: int = Field(ge=0)
    frameId: int | None = Field(default=None, ge=0)
    windowId: int | None = Field(default=None, ge=0)
    url: str | None = None
    title: str | None = None
    documentEpoch: int = Field(default=0, ge=0)
    documentId: str | None = None
    pageNonce: str | None = None


class BrowserAssistPageState(BaseModel):
    url: str
    title: str
    scrollX: int
    scrollY: int
    viewportWidth: int
    viewportHeight: int
    devicePixelRatio: float = Field(gt=0)
    documentEpoch: int = Field(default=0, ge=0)
    documentId: str | None = None
    pageNonce: str | None = None


class BrowserAssistViewportState(BaseModel):
    offsetLeft: int = 0
    offsetTop: int = 0
    scale: float = Field(default=1.0, gt=0)


class BrowserAssistBrowserRawGeometry(BaseModel):
    screenX: int | None = None
    screenY: int | None = None
    outerWidth: int | None = None
    outerHeight: int | None = None
    innerWidth: int | None = None
    innerHeight: int | None = None
    inferredLeftInset: int | None = None
    inferredTopInset: int | None = None


class BrowserAssistBrowserAnchor(BaseModel):
    contentLeftOnScreen: int
    contentTopOnScreen: int
    raw: BrowserAssistBrowserRawGeometry | None = None


class BrowserAssistRect(BaseModel):
    left: int
    top: int
    width: int
    height: int
    right: int
    bottom: int


class BrowserAssistClickablePoint(BaseModel):
    x: int
    y: int


class BrowserAssistLocatorRecipe(BaseModel):
    role: LocatorRole | None = None
    text: str | None = None
    selectorHint: str | None = None
    ancestorHints: list[str] = Field(default_factory=list)
    indexHint: int | None = Field(default=None, ge=0)


class BrowserAssistNodeRef(BaseModel):
    nodeId: str
    tabSessionId: str | None = None
    frameId: int | None = Field(default=None, ge=0)
    documentEpoch: int = Field(default=0, ge=0)
    documentId: str | None = None
    pageNonce: str | None = None
    selectorHint: str | None = None
    locatorRecipe: BrowserAssistLocatorRecipe = Field(default_factory=BrowserAssistLocatorRecipe)


class BrowserAssistActionability(BaseModel):
    sameSession: bool = True
    attached: bool = False
    visible: bool = False
    notOccluded: bool = False
    enabled: bool = False
    editable: bool | None = None
    stable: bool = False


class BrowserAssistMatch(BaseModel):
    id: str | None = None
    text: str
    textRaw: str | None = None
    normalizedText: str | None = None
    role: LocatorRole | None = None
    tagName: str
    selectorHint: str | None = None
    rect: BrowserAssistRect
    visibleRect: BrowserAssistRect | None = None
    nodeRef: BrowserAssistNodeRef | None = None
    clickablePoint: BrowserAssistClickablePoint
    actionability: BrowserAssistActionability | None = None
    visibleRatio: float | None = Field(default=None, ge=0, le=1)
    fullyVisible: bool | None = None
    occluded: bool | None = None
    selected: bool | None = None
    actionabilityScore: float | None = None
    score: float | None = None


class BrowserAssistFlags(BaseModel):
    bodyContainsSecurityText: bool = False
    isSecurityPage: bool = False


class BrowserAssistLocateResponse(BaseModel):
    context: BrowserTabSession | None = None
    page: BrowserAssistPageState
    viewport: BrowserAssistViewportState
    browser: BrowserAssistBrowserAnchor
    flags: BrowserAssistFlags = Field(default_factory=BrowserAssistFlags)
    matchCount: int = Field(ge=0)
    matches: list[BrowserAssistMatch] = Field(default_factory=list)


class BrowserAssistObserveRequest(BaseModel):
    nodeRef: BrowserAssistNodeRef


class BrowserAssistObservation(BaseModel):
    nodeRef: BrowserAssistNodeRef | None = None
    exists: bool = True
    text: str | None = None
    textRaw: str | None = None
    value: str | None = None
    selected: bool | None = None
    actionability: BrowserAssistActionability | None = None


class BrowserAssistObserveResponse(BaseModel):
    context: BrowserTabSession | None = None
    observation: BrowserAssistObservation


class BrowserAssistVerifySpec(BaseModel):
    kind: BrowserAssistVerifyKind
    timeoutMs: int = Field(default=2000, ge=0, le=15000)
    pollIntervalMs: int = Field(default=100, ge=10, le=1000)
    params: dict[str, Any] = Field(default_factory=dict)


class BrowserAssistActRequest(BaseModel):
    action: BrowserAssistActionKind
    tabSessionId: str | None = None
    nodeRef: BrowserAssistNodeRef | None = None
    text: str | None = None
    url: str | None = None
    verify: BrowserAssistVerifySpec | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "BrowserAssistActRequest":
        if self.action in {"click", "type"} and self.nodeRef is None:
            raise ValueError(f"{self.action} requires nodeRef.")
        if self.action == "type" and self.text is None:
            raise ValueError("type requires text.")
        if self.action == "navigate" and self.url is None:
            raise ValueError("navigate requires url.")
        return self


class BrowserAssistActResponse(BaseModel):
    context: BrowserTabSession | None = None
    nodeRef: BrowserAssistNodeRef | None = None
    action: BrowserAssistActionKind
    actionability: BrowserAssistActionability | None = None
    verified: bool
    verificationStatus: BrowserAssistVerificationStatus = "not_requested"
    retryDisposition: RetryDisposition = RetryDisposition.FAIL_FAST
    failureReason: str | None = None
    observation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_verification_status(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        observation = payload.get("observation")
        skipped = isinstance(observation, dict) and observation.get("verificationSkipped") is True
        if skipped:
            payload["verified"] = False
            payload["verificationStatus"] = "not_requested"
        elif not payload.get("verificationStatus"):
            payload["verificationStatus"] = "passed" if payload.get("verified") is True else "failed"
        return payload


class BrowserAssistStatusResponse(BaseModel):
    connected: bool
    token: str
    protocolVersion: int = 1
    lastSeenAt: str | None = None
    lastError: str | None = None
    extensionVersion: str | None = None
    browserName: str | None = None
    browserVersion: str | None = None
    lastPageUrl: str | None = None
    lastPageTitle: str | None = None
    currentTabSessionId: str | None = None
    preferredTabSessionId: str | None = None
    currentTabId: int | None = None
    currentFrameId: int | None = None
    currentWindowId: int | None = None
    currentDocumentEpoch: int | None = None
    currentDocumentId: str | None = None
    currentPageNonce: str | None = None


class BrowserAssistEnvelope(BaseModel):
    type: BrowserAssistMessageType
    requestId: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
