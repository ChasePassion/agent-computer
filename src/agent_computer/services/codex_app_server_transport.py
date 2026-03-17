from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import shutil
import threading
from typing import Any, Callable
from uuid import uuid4


class CodexAppServerTransportError(RuntimeError):
    pass


class CodexAppServerResponseError(CodexAppServerTransportError):
    def __init__(self, *, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class _PendingRequest:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class CodexAppServerTransport:
    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        cwd: str | Path | None = None,
        config_overrides: tuple[str, ...] = (),
        env: dict[str, str] | None = None,
        client_name: str = "agent_computer",
        client_title: str = "Agent Computer",
        client_version: str = "0.1.0",
        experimental_api: bool = False,
        notification_handler: Callable[[str, dict[str, Any]], None] | None = None,
        request_timeout_sec: float = 180.0,
    ) -> None:
        self.codex_bin = codex_bin
        self.cwd = None if cwd is None else str(Path(cwd))
        self.config_overrides = tuple(config_overrides)
        self.env = dict(env or {})
        self.client_name = client_name
        self.client_title = client_title
        self.client_version = client_version
        self.experimental_api = experimental_api
        self.notification_handler = notification_handler
        self.request_timeout_sec = max(1.0, float(request_timeout_sec))
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._pending: dict[str, _PendingRequest] = {}
        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._started = False
        self._closed = False

    def is_running(self) -> bool:
        with self._lock:
            proc = self._proc
            if self._closed or proc is None:
                return False
            return proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            args = [self._resolve_codex_bin()]
            for item in self.config_overrides:
                args.extend(["--config", item])
            args.extend(["app-server", "--listen", "stdio://"])
            env = os.environ.copy()
            env.update(self.env)
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.cwd,
                env=env,
                bufsize=1,
            )
            self._closed = False
            self._reader_thread = threading.Thread(target=self._reader_loop, name="agent-computer-codex-reader", daemon=True)
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(target=self._stderr_loop, name="agent-computer-codex-stderr", daemon=True)
            self._stderr_thread.start()
            self._started = True
        try:
            self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": self.client_name,
                        "title": self.client_title,
                        "version": self.client_version,
                    },
                    "capabilities": {
                        "experimentalApi": self.experimental_api,
                    },
                },
            )
            self.notify("initialized", {})
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._closed = True
            self._started = False
            pending = list(self._pending.values())
            self._pending.clear()
        for item in pending:
            item.error = CodexAppServerTransportError("Transport closed.")
            item.event.set()
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=0.5)

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: float | None = None) -> Any:
        self.start()
        request_id = str(uuid4())
        pending = _PendingRequest()
        with self._lock:
            self._pending[request_id] = pending
        try:
            self._write_message({"id": request_id, "method": method, "params": params or {}})
            if not pending.event.wait(timeout=timeout_sec or self.request_timeout_sec):
                raise CodexAppServerTransportError(f"Timed out waiting for response to {method}.")
            if pending.error is not None:
                raise pending.error
            return pending.result
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.start()
        self._write_message({"method": method, "params": params or {}})

    def _write_message(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise CodexAppServerTransportError("app-server is not running")
        with self._write_lock:
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                self._handle_message(message)
        finally:
            with self._lock:
                self._started = False
                self._closed = True
            self._fail_pending(CodexAppServerTransportError(f"app-server stdout closed. stderr_tail={self.stderr_tail()}"))
            self._emit_notification("__transport_error__", {"message": f"app-server stdout closed. stderr_tail={self.stderr_tail()}"})

    def _stderr_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw_line in proc.stderr:
            line = raw_line.rstrip("\n")
            with self._lock:
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > 120:
                    self._stderr_lines = self._stderr_lines[-120:]

    def stderr_tail(self, limit: int = 20) -> str:
        with self._lock:
            return "\n".join(self._stderr_lines[-limit:])

    def _resolve_codex_bin(self) -> str:
        configured = self.codex_bin.strip()
        candidate_path = Path(configured)
        if candidate_path.exists():
            return str(candidate_path)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        if os.name == "nt":
            appdata = os.getenv("APPDATA", "").strip()
            if appdata:
                npm_dir = Path(appdata) / "npm"
                for candidate in (
                    npm_dir / configured,
                    npm_dir / f"{configured}.cmd",
                    npm_dir / f"{configured}.ps1",
                    npm_dir / f"{configured}.exe",
                ):
                    if candidate.exists():
                        return str(candidate)
        return configured

    def _handle_message(self, message: dict[str, Any]) -> None:
        if "method" in message and "id" not in message:
            method = str(message.get("method") or "")
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            self._emit_notification(method, params)
            return

        if "method" in message and "id" in message:
            request_id = message.get("id")
            method = str(message.get("method") or "")
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            response: dict[str, Any]
            try:
                result = self._handle_server_request(method, params)
                response = {"id": request_id, "result": result}
            except Exception as exc:  # noqa: BLE001
                response = {
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": str(exc),
                    },
                }
            self._write_message(response)
            return

        request_id = str(message.get("id") or "")
        if not request_id:
            return
        with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return
        if "error" in message:
            error = message.get("error")
            if isinstance(error, dict):
                pending.error = CodexAppServerResponseError(
                    code=int(error.get("code", -32000)),
                    message=str(error.get("message", "unknown")),
                    data=error.get("data"),
                )
            else:
                pending.error = CodexAppServerTransportError("Malformed JSON-RPC error response.")
        else:
            pending.result = message.get("result")
        pending.event.set()

    def _handle_server_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._emit_notification("__server_request__", {"method": method, "params": params})
        if method == "item/commandExecution/requestApproval":
            return {"decision": "reject"}
        if method == "item/fileChange/requestApproval":
            return {"decision": "reject"}
        if method == "tool/requestUserInput":
            return {"answers": []}
        if method == "item/requestPermissions":
            return {"decision": "reject"}
        return {}

    def _emit_notification(self, method: str, params: dict[str, Any]) -> None:
        if self.notification_handler is None:
            return
        try:
            self.notification_handler(method, params)
        except Exception:
            return

    def _fail_pending(self, error: BaseException) -> None:
        with self._lock:
            pending_items = list(self._pending.values())
            self._pending.clear()
        for pending in pending_items:
            pending.error = error
            pending.event.set()
