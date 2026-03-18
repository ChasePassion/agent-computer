from __future__ import annotations

from enum import Enum
from typing import Any


class RetryDisposition(str, Enum):
    RETRY_SAME_TARGET = "retry_same_target"
    REACQUIRE_TARGET = "reacquire_target"
    CONTEXT_LOST = "context_lost"
    FAIL_FAST = "fail_fast"


def normalize_retry_disposition(
    value: str | RetryDisposition | None,
    default: RetryDisposition = RetryDisposition.FAIL_FAST,
) -> RetryDisposition:
    if isinstance(value, RetryDisposition):
        return value

    candidate = str(value or "").strip().lower()
    for item in RetryDisposition:
        if item.value == candidate:
            return item
    return default


def classify_browser_assist_error(
    message: str | None,
    *,
    default: RetryDisposition = RetryDisposition.FAIL_FAST,
) -> RetryDisposition:
    text = str(message or "").strip().lower()
    if not text:
        return default

    if "timed out" in text or "timeout" in text or "loading" in text or "temporarily" in text:
        return RetryDisposition.RETRY_SAME_TARGET

    if "documentepoch" in text or "document epoch" in text or "stale" in text or "node ref" in text or "noderef" in text:
        return RetryDisposition.REACQUIRE_TARGET

    if (
        "context_lost" in text
        or "tab session" in text
        or "not connected" in text
        or "disconnected" in text
        or "no active browser tab" in text
        or "unsupported browser assist tab url" in text
    ):
        return RetryDisposition.CONTEXT_LOST

    return default


class RetryDispositionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retry_disposition: RetryDisposition,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_disposition = retry_disposition
        self.details = details or {}
