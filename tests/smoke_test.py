from __future__ import annotations

import subprocess
import sys

import agent_computer


def run_module(module: str) -> None:
    subprocess.run(
        [sys.executable, "-m", module, "--help"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> None:
    assert agent_computer.__version__ == "0.1.0"
    run_module("agent_computer.cli")
    run_module("agent_computer.daemon")
    print("smoke ok")


if __name__ == "__main__":
    main()
