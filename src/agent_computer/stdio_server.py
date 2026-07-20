from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from agent_computer.client import DaemonClient


def _write_response(destination: TextIO, payload: dict[str, Any]) -> None:
    destination.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    destination.flush()


def run_stdio(source: TextIO, destination: TextIO, *, client: DaemonClient | Any | None = None) -> None:
    active_client = client or DaemonClient()
    owns_client = client is None
    try:
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue
            request_id: Any = None
            try:
                envelope = json.loads(line)
                if not isinstance(envelope, dict):
                    raise ValueError("Each input line must be a JSON object.")
                request_id = envelope.get("id")
                method = str(envelope.get("method") or "").strip().upper()
                path = str(envelope.get("path") or "").strip()
                payload = envelope.get("payload")
                if not method or not path.startswith("/"):
                    raise ValueError("Request requires an HTTP method and an absolute daemon path.")
                if payload is not None and not isinstance(payload, dict):
                    raise ValueError("payload must be a JSON object or null.")
                result = active_client.request(method, path, payload)
                _write_response(destination, {"id": request_id, "ok": True, "result": result})
            except Exception as exc:
                _write_response(
                    destination,
                    {
                        "id": request_id,
                        "ok": False,
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    },
                )
    finally:
        if owns_client and hasattr(active_client, "close"):
            active_client.close()


def main() -> None:
    run_stdio(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()

