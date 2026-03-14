from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

LocatorRole = Literal["button", "link", "input", "textarea", "tab", "checkbox", "radio", "any"]
BrowserAssistMessageType = Literal["hello", "keepalive", "locate", "locate-result", "error"]


class BrowserAssistQuery(BaseModel):
    text: str | None = None
    role: LocatorRole = "any"
    hint: str | None = None
    selectorHint: str | None = None
    index: int = Field(default=0, ge=0)


class BrowserAssistOptions(BaseModel):
    visibleOnly: bool = True
    interactiveOnly: bool = True
    maxCandidates: int = Field(default=5, ge=1, le=20)


class BrowserAssistLocateRequest(BaseModel):
    query: BrowserAssistQuery
    options: BrowserAssistOptions = Field(default_factory=BrowserAssistOptions)


class BrowserAssistPageState(BaseModel):
    url: str
    title: str
    scrollX: int
    scrollY: int
    viewportWidth: int
    viewportHeight: int
    devicePixelRatio: float = Field(gt=0)


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


class BrowserAssistMatch(BaseModel):
    id: str | None = None
    text: str
    role: LocatorRole | None = None
    tagName: str
    selectorHint: str | None = None
    rect: BrowserAssistRect
    clickablePoint: BrowserAssistClickablePoint


class BrowserAssistFlags(BaseModel):
    bodyContainsSecurityText: bool = False
    isSecurityPage: bool = False


class BrowserAssistRawResult(BaseModel):
    page: BrowserAssistPageState
    viewport: BrowserAssistViewportState
    browser: BrowserAssistBrowserAnchor
    flags: BrowserAssistFlags = Field(default_factory=BrowserAssistFlags)
    matchCount: int = Field(ge=0)
    matches: list[BrowserAssistMatch] = Field(default_factory=list)


class BrowserAssistScreenPoint(BaseModel):
    x: int
    y: int


class BrowserAssistMappedCandidate(BaseModel):
    id: str
    text: str
    tagName: str
    screenPoint: BrowserAssistScreenPoint
    gridPoint: BrowserAssistScreenPoint
    cssAbsolutePoint: BrowserAssistScreenPoint
    rect: BrowserAssistRect


class BrowserAssistMappedResult(BaseModel):
    screenCandidates: list[BrowserAssistMappedCandidate]


class BrowserAssistLocateResponse(BaseModel):
    raw: BrowserAssistRawResult
    mapped: BrowserAssistMappedResult


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


class BrowserAssistEnvelope(BaseModel):
    type: BrowserAssistMessageType
    requestId: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
