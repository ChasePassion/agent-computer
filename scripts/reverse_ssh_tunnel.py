from __future__ import annotations

import argparse
import select
import socket
import sys
import threading

import paramiko


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


def run_reverse_tunnel(
    *,
    relay_host: str,
    relay_user: str,
    relay_password: str,
    ssh_port: int,
    remote_port: int,
    local_host: str,
    local_port: int,
) -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=relay_host,
        port=ssh_port,
        username=relay_user,
        password=relay_password,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
    )
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is not available.")
    transport.set_keepalive(30)
    transport.request_port_forward("127.0.0.1", remote_port)

    print(f"Opening reverse SSH tunnel to {relay_user}@{relay_host} ...")
    print(f"Remote: 127.0.0.1:{remote_port} -> Local: {local_host}:{local_port}")
    print("")
    print("Keep this window open while you need remote access.")
    sys.stdout.flush()

    try:
        while True:
            channel = transport.accept(timeout=1.0)
            if channel is None:
                continue
            thread = threading.Thread(
                target=bridge_channel,
                args=(channel, local_host, local_port),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open a reverse SSH tunnel using paramiko.")
    parser.add_argument("--relay-host", required=True)
    parser.add_argument("--relay-user", required=True)
    parser.add_argument("--relay-password", required=True)
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=37688)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_reverse_tunnel(
        relay_host=args.relay_host,
        relay_user=args.relay_user,
        relay_password=args.relay_password,
        ssh_port=args.ssh_port,
        remote_port=args.remote_port,
        local_host=args.local_host,
        local_port=args.local_port,
    )


if __name__ == "__main__":
    raise SystemExit(main())
