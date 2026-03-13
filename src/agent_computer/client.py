from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

import httpx

from agent_computer.runtime import DEFAULT_HOST, DEFAULT_HTTP_TIMEOUT_SEC, DEFAULT_PORT, DEFAULT_STARTUP_TIMEOUT_SEC, PROJECT_ROOT, daemon_base_url


class DaemonClient:
    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC,
        startup_timeout_sec: float = DEFAULT_STARTUP_TIMEOUT_SEC,
    ) -> None:
        self.host = host
        self.port = port
        self.base_url = daemon_base_url(host, port)
        self.timeout_sec = timeout_sec
        self.startup_timeout_sec = startup_timeout_sec

    def _http_client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout_sec)

    def health(self) -> dict[str, Any]:
        with self._http_client() as client:
            response = client.get("/system/health")
            response.raise_for_status()
            return response.json()

    def is_running(self) -> bool:
        try:
            self.health()
            return True
        except Exception:
            return False

    def start_background(self) -> None:
        if self.is_running():
            return

        command = [
            str(sys.executable),
            "-m",
            "agent_computer.daemon",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        kwargs: dict[str, Any] = {
            "cwd": str(PROJECT_ROOT),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(command, **kwargs)

    def wait_until_ready(self) -> dict[str, Any]:
        deadline = time.time() + self.startup_timeout_sec
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                return self.health()
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        raise RuntimeError("Timed out waiting for agent-computer daemon to become ready.") from last_error

    def ensure_running(self) -> dict[str, Any]:
        if self.is_running():
            return self.health()
        self.start_background()
        return self.wait_until_ready()

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        self.ensure_running()
        with self._http_client() as client:
            response = client.request(method=method, url=path, json=payload)
            response.raise_for_status()
            return response.json()

    def shutdown(self) -> dict[str, Any]:
        with self._http_client() as client:
            response = client.post("/system/shutdown")
            response.raise_for_status()
            return response.json()
