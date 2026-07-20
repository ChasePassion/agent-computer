from __future__ import annotations

import subprocess
import sys


def test_cli_import_does_not_load_desktop_or_server_stacks() -> None:
    script = """
import sys
import agent_computer.cli
heavy = {
    'agent_computer.actions',
    'agent_computer.capture',
    'agent_computer.daemon',
    'agent_computer.models.browser_assist',
}
loaded = sorted(heavy.intersection(sys.modules))
if loaded:
    raise SystemExit('loaded heavy modules: ' + ','.join(loaded))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
