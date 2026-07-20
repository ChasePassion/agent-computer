from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Any

import httpx

from agent_computer.runtime import (
    DEFAULT_BIND_HOST,
    DEFAULT_HOST,
    DEFAULT_HTTP_TIMEOUT_SEC,
    DEFAULT_PORT,
    DEFAULT_STARTUP_TIMEOUT_SEC,
    PROJECT_ROOT,
    daemon_base_url,
)


class DaemonClient:
    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        bind_host: str = DEFAULT_BIND_HOST,
        port: int = DEFAULT_PORT,
        timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC,
        startup_timeout_sec: float = DEFAULT_STARTUP_TIMEOUT_SEC,
    ) -> None:
        self.host = host
        self.bind_host = bind_host
        self.port = port
        self.base_url = daemon_base_url(host, port)
        self.timeout_sec = timeout_sec
        self.startup_timeout_sec = startup_timeout_sec
        self._client: httpx.Client | None = None
        self._client_lock = threading.RLock()
        self._startup_lock = threading.Lock()

    def _http_client(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_sec)
            return self._client

    def close(self) -> None:
        with self._client_lock:
            client = self._client
            self._client = None
        if client is not None and not client.is_closed:
            client.close()

    def __enter__(self) -> "DaemonClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        response = self._http_client().get("/system/health")
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

        self._spawn_background()

    def _spawn_background(self) -> None:

        command = [
            str(sys.executable),
            "-m",
            "agent_computer.daemon",
            "--host",
            self.bind_host,
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
        try:
            return self.health()
        except httpx.TransportError:
            self._spawn_background()
            return self.wait_until_ready()

    def _request_once(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = self._http_client().request(method=method, url=path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        # The hot path is one business request. Starting the daemon is only a
        # recovery path after a real transport failure, avoiding health probes
        # before every atomic agent action.
        try:
            return self._request_once(method, path, payload, headers=headers)
        except httpx.ConnectError:
            with self._startup_lock:
                try:
                    return self._request_once(method, path, payload, headers=headers)
                except httpx.ConnectError:
                    self._spawn_background()
                    self.wait_until_ready()
            return self._request_once(method, path, payload, headers=headers)

    def shutdown(self) -> dict[str, Any]:
        response = self._http_client().post("/system/shutdown")
        response.raise_for_status()
        return response.json()
