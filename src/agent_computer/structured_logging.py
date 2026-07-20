from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from agent_computer.runtime import PROJECT_ROOT


LOG_DIR = PROJECT_ROOT / "logs"
LOG_PATH = LOG_DIR / "agent-computer.log"
_CONFIG_LOCK = threading.Lock()


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "module": record.name,
            "event": getattr(record, "event_name", "application.event"),
            "message": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def get_event_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(module)
    with _CONFIG_LOCK:
        if not any(getattr(handler, "_agent_computer_handler", False) for handler in logger.handlers):
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(JsonEventFormatter())
            handler._agent_computer_handler = True  # type: ignore[attr-defined]
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    *,
    event: str,
    message: str,
    outcome: str,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    safe_fields = {key: value for key, value in fields.items() if value is not None}
    safe_fields["outcome"] = outcome
    logger.info(
        message,
        extra={"event_name": event, "event_fields": safe_fields},
        exc_info=exc_info,
    )
