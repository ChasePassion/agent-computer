from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tunnel_manager.py"
SPEC = importlib.util.spec_from_file_location("tunnel_manager", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def build_transaction(tmp_path: Path) -> object:
    return MODULE.TunnelTransaction(
        relay_host="relay.example.com",
        relay_user="relay-user",
        relay_password=None,
        ssh_port=22,
        remote_port=43768,
        local_host="127.0.0.1",
        local_port=37688,
        state_path=tmp_path / "observation.tunnel.state.json",
    )


def test_parse_remote_listener_output_free() -> None:
    listener = MODULE.parse_remote_listener_output("FREE\n")

    assert listener.listening is False
    assert listener.pid is None
    assert listener.process_name is None


def test_parse_remote_listener_output_listening() -> None:
    listener = MODULE.parse_remote_listener_output(
        "LISTENING pid=1234 process=sshd raw=LISTEN raw-content\n"
    )

    assert listener.listening is True
    assert listener.pid == 1234
    assert listener.process_name == "sshd"


def test_is_stale_listener_when_remote_state_matches_previous_state(tmp_path: Path) -> None:
    transaction = build_transaction(tmp_path)
    probe = MODULE.RemoteProbeResult(
        listener=MODULE.RemoteListenerInfo(listening=True, pid=111, process_name="sshd"),
        remote_state={
            "relay_host": "relay.example.com",
            "relay_user": "relay-user",
            "remote_port": 43768,
            "owner_token": "token-1",
        },
    )
    previous_state = {
        "relay_host": "relay.example.com",
        "relay_user": "relay-user",
        "remote_port": 43768,
        "owner_token": "token-1",
    }

    assert transaction.is_stale_listener(probe, previous_state) is True


def test_is_stale_listener_rejects_unmanaged_process(tmp_path: Path) -> None:
    transaction = build_transaction(tmp_path)
    probe = MODULE.RemoteProbeResult(
        listener=MODULE.RemoteListenerInfo(listening=True, pid=222, process_name="python"),
        remote_state=None,
    )
    previous_state = {
        "relay_host": "relay.example.com",
        "relay_user": "relay-user",
        "remote_port": 43768,
    }

    assert transaction.is_stale_listener(probe, previous_state) is False
