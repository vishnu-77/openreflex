import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openreflex import install
from openreflex.project import approval

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "openreflex"


def test_claude_code_install_merges_and_is_idempotent(project):
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir()
    user_hook = {"hooks": [{"type": "command", "command": "echo mine"}]}
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [user_hook]}}))
    assert install.install("claude-code", project)
    data = json.loads(settings.read_text())
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    assert data["hooks"]["Stop"][0] == user_hook and len(data["hooks"]["Stop"]) == 2
    assert json.loads((project / ".mcp.json").read_text())["mcpServers"]["openreflex"]["args"] == ["mcp"]
    assert install.install("claude-code", project) == [], "second install changes nothing"
    assert approval(project) is not None


@pytest.mark.parametrize("agent, expected", [
    ("codex", [".codex/hooks.json", ".codex/config.toml"]),
    ("cursor", [".cursor/hooks.json", ".cursor/mcp.json"]),
    ("opencode", [".opencode/plugins/openreflex.ts", "opencode.json"]),
])
def test_other_agent_installs(project, agent, expected):
    install.install(agent, project)
    for relative in expected:
        assert (project / relative).exists(), relative
    if agent == "codex":
        install.install(agent, project)
        assert (project / ".codex/config.toml").read_text().count("[mcp_servers.openreflex]") == 1


def test_dry_run_writes_nothing(project):
    assert install.install("cursor", project, dry_run=True)
    assert not (project / ".cursor").exists() and approval(project) is None


def test_plugin_hook_files_match_installer_definitions():
    claude = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert claude["hooks"] == install.claude_style_hooks("claude-code", install.CLAUDE_EVENTS)["hooks"]
    assert json.loads((PLUGIN / "hooks" / "codex-hooks.json").read_text()) == \
        install.claude_style_hooks("codex", install.CODEX_EVENTS)
    assert json.loads((PLUGIN / "hooks" / "cursor-hooks.json").read_text()) == install.cursor_hooks()
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    cursor = json.loads((PLUGIN / ".cursor-plugin" / "plugin.json").read_text())
    assert codex["hooks"] == "./hooks/codex-hooks.json", "Codex must not read the Claude Code hooks.json"
    assert cursor["hooks"] == "./hooks/cursor-hooks.json"
    for manifest in (codex, cursor):
        assert (PLUGIN / manifest["mcpServers"]).exists() and (PLUGIN / manifest["skills"]).is_dir()


def _run(args, stdin="", env_home=None, cwd=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "OPENREFLEX_HOME": str(env_home)}
    return subprocess.run([sys.executable, "-m", "openreflex", *args], input=stdin.encode(), capture_output=True,
                          env=env, cwd=cwd, timeout=60)


def test_cli_hook_never_blocks_even_with_bad_arguments(isolated_home, project):
    for args in (["hook"], ["hook", "nonsense-agent", "PostToolUse"], ["hook", "claude-code", "PostToolUse"]):
        result = _run(args, stdin="{broken", env_home=isolated_home, cwd=project)
        assert result.returncode == 0, (args, result.stderr)


def test_cli_end_to_end_capture_via_subprocess(isolated_home, project):
    assert _run(["approve", "--project", str(project)], env_home=isolated_home).returncode == 0
    base = {"session_id": "cli", "cwd": str(project)}
    events = [
        ("UserPromptSubmit", {**base, "prompt": "Fix the unicode filename bug in the upload handler"}),
        ("PreToolUse", {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/upload.py"}, "tool_use_id": "1"}),
        ("PostToolUse", {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/upload.py"}, "tool_use_id": "1",
                         "tool_response": {"filePath": "src/upload.py"}}),
        ("PreToolUse", {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "2"}),
        ("PostToolUse", {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "2",
                         "tool_response": {"stdout": "3 passed ✓", "stderr": ""}}),
        ("Stop", base),
    ]
    for event, payload in events:
        result = _run(["hook", "claude-code", event], stdin=json.dumps(payload), env_home=isolated_home)
        assert result.returncode == 0 and not result.stderr, result.stderr
    status = _run(["status", "--json", "--project", str(project)], env_home=isolated_home)
    data = json.loads(status.stdout)
    assert data["engagement"]["experiences"] == 1 and data["outcomes"]["success_rate"] == 1.0
    assert data["activation"]["first_session_captured"] is True
    preview = _run(["context", "Fix unicode filename handling in uploads", "--project", str(project)], env_home=isolated_home)
    assert "src/upload.py" in preview.stdout.decode()
    assert not (isolated_home / "logs" / "errors.log").exists()
