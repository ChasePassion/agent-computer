from __future__ import annotations

import argparse

import uvicorn

from agent_computer.api import create_app
from agent_computer.runtime import DEFAULT_HOST, DEFAULT_PORT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-computer-daemon", description="Run the Agent Computer daemon.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Bind port.")
    parser.add_argument("--log-level", default="warning", help="Uvicorn log level.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    app = create_app(host=args.host, port=args.port)
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level=args.log_level)
    server = uvicorn.Server(config)
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
