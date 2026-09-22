"""End-to-end smoke for Claude plugin onboarding and the managed runtime supervisor.

This intentionally places a fake stale `openreflex` first on PATH. The plugin launcher must
ignore it, install the exact plugin-version wheel into its private runtime, enable one project
through explicit onboarding, and capture the first task through the real hook path.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "openreflex"
LAUNCHER = PLUGIN / "runtime" / "launcher.cjs"


def main() -> int:
    assert len(sys.argv) == 2, "usage: smoke_plugin_onboarding.py <wheel>"
    wheel = Path(sys.argv[1]).resolve()
    assert wheel.exists(), wheel
    node = shutil.which("node")
    assert node, "Node.js is required by the Claude plugin launcher"

    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    expected = manifest["version"]

    tmp = Path(tempfile.mkdtemp(prefix="openreflex-plugin-smoke-"))
    home = tmp / "home"
    project = tmp / "repo"
    old_bin = tmp / "old-bin"
    sentinel = tmp / "stale-runtime-was-called"
    (project / ".git").mkdir(parents=True)
    old_bin.mkdir()

    if os.name == "nt":
        stale = old_bin / "openreflex.bat"
        stale.write_text(f'@echo off\r\necho stale>"{sentinel}"\r\necho 0.3.2\r\nexit /b 99\r\n', encoding="utf-8")
    else:
        stale = old_bin / "openreflex"
        stale.write_text(
            f'#!/bin/sh\necho stale > "{sentinel}"\necho 0.3.2\nexit 99\n',
            encoding="utf-8",
        )
        stale.chmod(stale.stat().st_mode | stat.S_IEXEC)

    env = {
        **os.environ,
        "OPENREFLEX_HOME": str(home),
        "OPENREFLEX_BOOTSTRAP_SPEC": str(wheel),
        "PATH": str(old_bin) + os.pathsep + os.environ.get("PATH", ""),
    }
    env.pop("PYTHONPATH", None)

    def run(*args: str, stdin: str = "", timeout: int = 240) -> str:
        command = [node, str(LAUNCHER), *args, "--plugin-root", str(PLUGIN)]
        result = subprocess.run(
            command,
            input=stdin.encode(),
            capture_output=True,
            cwd=project,
            env=env,
            timeout=timeout,
            check=False,
        )
        assert result.returncode == 0, (command, result.stdout.decode(errors="replace"), result.stderr.decode(errors="replace"))
        return result.stdout.decode(errors="replace")

    onboard = run("onboard", "--project", str(project))
    assert "OPENREFLEX / READY" in onboard, onboard
    assert f"runtime     v{expected}" in onboard, onboard
    assert f"plugin      v{expected}" in onboard, onboard
    assert "runtime source   plugin-managed" in onboard, onboard
    assert "project memory   enabled" in onboard, onboard

    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    status_command = settings["statusLine"]["command"].replace("\\", "/")
    assert "/.openreflex/" not in status_command or "/runtime/" in status_command
    assert f"/runtime/v{expected}/" in status_command, status_command
    assert "openreflex statusline" != settings["statusLine"]["command"]

    base = {"session_id": "fresh-user", "cwd": str(project)}
    events = [
        ("UserPromptSubmit", {**base, "prompt": "Fix the date parsing bug in the importer"}),
        ("PreToolUse", {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}, "tool_use_id": "1"}),
        ("PostToolUse", {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}, "tool_use_id": "1",
                         "tool_response": {}}),
        ("PreToolUse", {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "2"}),
        ("PostToolUse", {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "2",
                         "tool_response": {"stdout": "1 passed"}}),
        ("Stop", base),
    ]
    for event, payload in events:
        run("hook", "claude-code", event, stdin=json.dumps(payload))

    tui = run("tui", "--project", str(project))
    assert f"OPENREFLEX v{expected}" in tui, tui
    assert "experiences      1" in tui, tui
    assert "project memory   enabled" in tui, tui
    assert "runtime source   plugin-managed" in tui, tui

    assert not sentinel.exists(), "plugin incorrectly executed the stale global openreflex from PATH"
    print("plugin onboarding smoke ok:", sys.platform, expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
