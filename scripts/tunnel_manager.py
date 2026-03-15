from __future__ import annotations

import argparse
import atexit
import json
import os
import select
import shlex
import signal
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paramiko


DEFAULT_REMOTE_BIND_HOST = "127.0.0.1"
REMOTE_STATE_DIR = "~/.agent-computer/tunnels"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def build_remote_state_path(remote_port: int) -> str:
    return f"{REMOTE_STATE_DIR}/observation-{remote_port}.json"


@dataclass
class RemoteListenerInfo:
    listening: bool
    pid: int | None = None
    process_name: str | None = None
    raw: str | None = None


@dataclass
class RemoteProbeResult:
    listener: RemoteListenerInfo
    remote_state: dict[str, Any] | None

    @property
    def listening(self) -> bool:
        return self.listener.listening


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json_dumps(payload) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def remove_file_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def bridge_channel(channel: paramiko.Channel, local_host: str, local_port: int) -> None:
    local_socket = socket.socket()
    try:
        local_socket.connect((local_host, local_port))
        while True:
            readable, _, _ = select.select([channel, local_socket], [], [])
            if channel in readable:
                data = channel.recv(4096)
                if not data:
                    break
                local_socket.sendall(data)
            if local_socket in readable:
                data = local_socket.recv(4096)
                if not data:
                    break
                channel.sendall(data)
    finally:
        try:
            channel.close()
        except Exception:
            pass
        try:
            local_socket.close()
        except Exception:
            pass


class RemoteCommandError(RuntimeError):
    pass


class TunnelTransaction:
    def __init__(
        self,
        *,
        relay_host: str,
        relay_user: str,
        relay_password: str | None,
        ssh_port: int,
        remote_port: int,
        local_host: str,
        local_port: int,
        state_path: Path,
        remote_bind_host: str = DEFAULT_REMOTE_BIND_HOST,
        probe_wait_seconds: float = 4.0,
    ) -> None:
        self.relay_host = relay_host
        self.relay_user = relay_user
        self.relay_password = relay_password
        self.ssh_port = ssh_port
        self.remote_port = remote_port
        self.local_host = local_host
        self.local_port = local_port
        self.state_path = state_path
        self.remote_bind_host = remote_bind_host
        self.probe_wait_seconds = probe_wait_seconds
        self.owner_token = str(uuid.uuid4())
        self.client: paramiko.SSHClient | None = None
        self.transport: paramiko.Transport | None = None
        self._stopping = False
        self._cleanup_started = False
        self._remote_state_written = False
        self._local_state_written = False

    def connect(self) -> None:
        client = self.create_client()
        transport = client.get_transport()
        if transport is None:
            client.close()
            raise RuntimeError("SSH transport is not available.")
        transport.set_keepalive(30)
        self.client = client
        self.transport = transport

    def run(self) -> int:
        self.connect()
        self.register_exit_hooks()
        try:
            self.start_transaction()
            return self.wait_forever()
        except Exception:
            self.cleanup()
            raise

    def start_transaction(self) -> None:
        previous_state = load_json_file(self.state_path)
        probe = self.probe_remote_state()
        if probe.listening:
            if self.is_stale_listener(probe, previous_state):
                self.cleanup_stale_remote_listener(probe)
                self.assert_remote_port_released()
            else:
                process_name = probe.listener.process_name or "unknown"
                pid = probe.listener.pid if probe.listener.pid is not None else "unknown"
                raise RuntimeError(
                    f"Remote port {self.remote_port} is already in use by unmanaged process "
                    f"{process_name} (pid={pid})."
                )

        assert self.transport is not None
        self.transport.request_port_forward(self.remote_bind_host, self.remote_port)
        self.write_remote_state()
        self.write_local_state(cleanup_pending=False)

        print(f"Opening reverse SSH tunnel to {self.relay_user}@{self.relay_host} ...")
        print(
            f"Remote: {self.remote_bind_host}:{self.remote_port} -> "
            f"Local: {self.local_host}:{self.local_port}"
        )
        print("")
        print("Keep this window open while you need remote access.")
        sys.stdout.flush()

    def wait_forever(self) -> int:
        assert self.transport is not None
        try:
            while not self._stopping:
                channel = self.transport.accept(timeout=1.0)
                if channel is None:
                    continue
                thread = threading.Thread(
                    target=bridge_channel,
                    args=(channel, self.local_host, self.local_port),
                    daemon=True,
                )
                thread.start()
            return 0
        except KeyboardInterrupt:
            self._stopping = True
            return 0
        finally:
            self.cleanup()

    def register_exit_hooks(self) -> None:
        def stop_handler(signum: int, _frame: Any) -> None:
            self._stopping = True

        for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, stop_handler)
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        if self._cleanup_started:
            return
        self._cleanup_started = True

        cleanup_pending = False
        try:
            self.close_local_transport()
            if not self.verify_remote_port_released():
                cleanup_pending = True
                probe = self.probe_remote_state()
                if probe.listening and self.is_stale_listener(probe, load_json_file(self.state_path)):
                    self.cleanup_stale_remote_listener(probe)
                    cleanup_pending = not self.verify_remote_port_released()
        except Exception:
            cleanup_pending = True
        finally:
            try:
                self.remove_remote_state()
            except Exception:
                cleanup_pending = True

            if cleanup_pending:
                self.write_local_state(cleanup_pending=True)
            else:
                remove_file_quietly(self.state_path)

    def close_local_transport(self) -> None:
        if self.transport is not None:
            try:
                self.transport.cancel_port_forward(self.remote_bind_host, self.remote_port)
            except Exception:
                pass
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.transport = None
        self.client = None

    def write_local_state(self, *, cleanup_pending: bool) -> None:
        payload = {
            "version": 1,
            "relay_host": self.relay_host,
            "relay_user": self.relay_user,
            "ssh_port": self.ssh_port,
            "remote_bind_host": self.remote_bind_host,
            "remote_port": self.remote_port,
            "local_host": self.local_host,
            "local_port": self.local_port,
            "owner_token": self.owner_token,
            "started_at": utc_now_iso(),
            "client_pid": os.getpid(),
            "mode": "paramiko",
            "cleanup_pending": cleanup_pending,
        }
        save_json_atomic(self.state_path, payload)
        self._local_state_written = True

    def write_remote_state(self) -> None:
        payload = {
            "version": 1,
            "relay_host": self.relay_host,
            "relay_user": self.relay_user,
            "ssh_port": self.ssh_port,
            "remote_bind_host": self.remote_bind_host,
            "remote_port": self.remote_port,
            "local_host": self.local_host,
            "local_port": self.local_port,
            "owner_token": self.owner_token,
            "started_at": utc_now_iso(),
            "client_pid": os.getpid(),
        }
        path = build_remote_state_path(self.remote_port)
        content = json_dumps(payload)
        command = (
            f"mkdir -p {shell_quote(REMOTE_STATE_DIR)} && "
            f"cat > {shell_quote(path)} <<'EOF'\n{content}\nEOF"
        )
        self.exec_remote(command)
        self._remote_state_written = True

    def remove_remote_state(self) -> None:
        path = build_remote_state_path(self.remote_port)
        self.exec_remote(f"rm -f {shell_quote(path)}", allow_fail=True)

    def probe_remote_state(self) -> RemoteProbeResult:
        listener = self.detect_remote_listener()
        remote_state = self.read_remote_state()
        return RemoteProbeResult(listener=listener, remote_state=remote_state)

    def detect_remote_listener(self) -> RemoteListenerInfo:
        port = self.remote_port
        script = f"""
port={shell_quote(str(port))}
line=""
if command -v ss >/dev/null 2>&1; then
  line=$(ss -lntp "( sport = :$port )" 2>/dev/null | awk 'NR>1 && $1 == "LISTEN" {{print; exit}}')
  if [ -n "$line" ]; then
    pid=$(printf '%s\n' "$line" | sed -n 's/.*pid=\\([0-9][0-9]*\\).*/\\1/p' | head -n1)
    proc=$(printf '%s\n' "$line" | sed -n 's/.*users:((\"\\([^\"]*\\)\".*/\\1/p' | head -n1)
    printf 'LISTENING pid=%s process=%s raw=%s\n' "${{pid:-}}" "${{proc:-}}" "$line"
    exit 0
  fi
fi
if command -v lsof >/dev/null 2>&1; then
  line=$(lsof -nP -iTCP:$port -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {{print; exit}}')
  if [ -n "$line" ]; then
    proc=$(printf '%s\n' "$line" | awk '{{print $1}}')
    pid=$(printf '%s\n' "$line" | awk '{{print $2}}')
    printf 'LISTENING pid=%s process=%s raw=%s\n' "${{pid:-}}" "${{proc:-}}" "$line"
    exit 0
  fi
fi
if command -v netstat >/dev/null 2>&1; then
  line=$(netstat -lntp 2>/dev/null | awk '$4 ~ /:'"$port"'$/ && $6 == "LISTEN" {{print; exit}}')
  if [ -n "$line" ]; then
    proc=$(printf '%s\n' "$line" | awk '{{print $7}}')
    pid=$(printf '%s\n' "$line" | cut -d/ -f1)
    pname=$(printf '%s\n' "$proc" | cut -d/ -f2)
    printf 'LISTENING pid=%s process=%s raw=%s\n' "${{pid:-}}" "${{pname:-}}" "$line"
    exit 0
  fi
fi
printf 'FREE\n'
"""
        stdout = self.exec_remote(script)
        return parse_remote_listener_output(stdout)

    def read_remote_state(self) -> dict[str, Any] | None:
        path = build_remote_state_path(self.remote_port)
        stdout = self.exec_remote(
            f"if [ -f {shell_quote(path)} ]; then cat {shell_quote(path)}; fi",
            allow_fail=True,
        )
        text = stdout.strip()
        if not text:
            return None
        return json.loads(text)

    def exec_remote(self, command: str, *, allow_fail: bool = False, shell_wrap: bool = True) -> str:
        created_client = False
        client = self.client
        if client is None:
            client = self.create_client()
            created_client = True
        remote_command = f"sh -lc {shell_quote(command)}" if shell_wrap else command
        try:
            stdin, stdout, stderr = client.exec_command(remote_command)
            del stdin
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace")
            errput = stderr.read().decode("utf-8", errors="replace")
            if exit_code != 0 and not allow_fail:
                raise RemoteCommandError(
                    f"Remote command failed with exit code {exit_code}: {errput.strip() or output.strip()}"
                )
            return output
        finally:
            if created_client:
                client.close()

    def create_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.relay_host,
            port=self.ssh_port,
            username=self.relay_user,
            password=self.relay_password,
            allow_agent=self.relay_password is None,
            look_for_keys=self.relay_password is None,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
        )
        return client

    def is_stale_listener(
        self,
        probe: RemoteProbeResult,
        previous_state: dict[str, Any] | None,
    ) -> bool:
        if not probe.listening:
            return False
        process_name = (probe.listener.process_name or "").lower()
        is_ssh_listener = "ssh" in process_name
        if probe.remote_state and probe.remote_state.get("owner_token"):
            owner_token = previous_state.get("owner_token") if previous_state else None
            return (
                probe.remote_state.get("relay_host") == self.relay_host
                and probe.remote_state.get("relay_user") == self.relay_user
                and int(probe.remote_state.get("remote_port", -1)) == self.remote_port
                and (owner_token is None or probe.remote_state.get("owner_token") == owner_token)
            )

        if previous_state:
            return (
                is_ssh_listener
                and previous_state.get("relay_host") == self.relay_host
                and previous_state.get("relay_user") == self.relay_user
                and int(previous_state.get("remote_port", -1)) == self.remote_port
            )
        return False

    def cleanup_stale_remote_listener(self, probe: RemoteProbeResult) -> None:
        pid = probe.listener.pid
        if pid is None:
            raise RuntimeError(
                f"Cannot cleanup stale remote listener on port {self.remote_port}: missing pid."
            )

        self.exec_remote(f"kill -TERM {pid}", allow_fail=True)
        if self.wait_for_remote_port_release(timeout_seconds=self.probe_wait_seconds):
            self.remove_remote_state()
            return

        self.exec_remote(f"kill -KILL {pid}", allow_fail=True)
        if not self.wait_for_remote_port_release(timeout_seconds=self.probe_wait_seconds):
            raise RuntimeError(
                f"Failed to cleanup stale remote listener on port {self.remote_port}."
            )
        self.remove_remote_state()

    def assert_remote_port_released(self) -> None:
        if not self.wait_for_remote_port_release(timeout_seconds=self.probe_wait_seconds):
            raise RuntimeError(
                f"Remote port {self.remote_port} is still listening after cleanup."
            )

    def verify_remote_port_released(self) -> bool:
        try:
            return self.wait_for_remote_port_release(timeout_seconds=self.probe_wait_seconds)
        except Exception:
            return False

    def wait_for_remote_port_release(self, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            probe = self.probe_remote_state()
            if not probe.listening:
                return True
            time.sleep(0.5)
        return not self.probe_remote_state().listening


def parse_remote_listener_output(output: str) -> RemoteListenerInfo:
    text = output.strip()
    if not text or text == "FREE":
        return RemoteListenerInfo(listening=False)
    if not text.startswith("LISTENING"):
        raise ValueError(f"Unexpected remote listener output: {text}")

    pid: int | None = None
    process_name: str | None = None
    raw: str | None = None
    for token in text.split()[1:]:
        if token.startswith("pid="):
            value = token.removeprefix("pid=")
            if value.isdigit():
                pid = int(value)
        elif token.startswith("process="):
            value = token.removeprefix("process=")
            process_name = None if value == "" else value
        elif token.startswith("raw="):
            raw = token.removeprefix("raw=")

    return RemoteListenerInfo(listening=True, pid=pid, process_name=process_name, raw=raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage observation reverse tunnel transactionally.")
    parser.add_argument("--relay-host", required=True)
    parser.add_argument("--relay-user", required=True)
    parser.add_argument("--relay-password")
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=37688)
    parser.add_argument(
        "--state-path",
        default=str(Path(".agent") / "observation.tunnel.state.json"),
    )
    parser.add_argument("--remote-bind-host", default=DEFAULT_REMOTE_BIND_HOST)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    transaction = TunnelTransaction(
        relay_host=args.relay_host,
        relay_user=args.relay_user,
        relay_password=args.relay_password,
        ssh_port=args.ssh_port,
        remote_port=args.remote_port,
        local_host=args.local_host,
        local_port=args.local_port,
        state_path=Path(args.state_path),
        remote_bind_host=args.remote_bind_host,
    )
    return transaction.run()


if __name__ == "__main__":
    raise SystemExit(main())
