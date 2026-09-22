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
    assert not (project / ".mcp.json").exists(), "ambient install must not expose MCP by default"
    assert install.install("claude-code", project) == [], "second install changes nothing"
    assert approval(project) is not None


@pytest.mark.parametrize("agent, expected", [
    ("codex", [".codex/hooks.json"]),
    ("cursor", [".cursor/hooks.json"]),
    ("opencode", [".opencode/plugins/openreflex.ts"]),
])
def test_other_agent_installs(project, agent, expected):
    install.install(agent, project)
    for relative in expected:
        assert (project / relative).exists(), relative
    if agent == "codex":
        assert not (project / ".codex/config.toml").exists()
    if agent == "cursor":
        assert not (project / ".cursor/mcp.json").exists()
    if agent == "opencode":
        assert not (project / "opencode.json").exists()


def test_dry_run_writes_nothing(project):
    assert install.install("cursor", project, dry_run=True)
    assert not (project / ".cursor").exists() and approval(project) is None


def test_default_install_removes_legacy_model_facing_mcp_config(project):
    legacy = project / ".mcp.json"
    legacy.write_text(json.dumps({
        "mcpServers": {
            "openreflex": {"command": "openreflex", "args": ["mcp"]},
            "user-owned": {"command": "other-server"},
        }
    }), encoding="utf-8")

    install.install("claude-code", project)

    data = json.loads(legacy.read_text(encoding="utf-8"))
    assert "openreflex" not in data["mcpServers"]
    assert data["mcpServers"]["user-owned"] == {"command": "other-server"}
    assert "openreflex hook" in (project / ".claude" / "settings.json").read_text(encoding="utf-8")


def test_plugin_hook_files_match_installer_definitions():
    claude = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert claude["hooks"] == install.claude_plugin_hooks()["hooks"]
    assert json.loads((PLUGIN / "hooks" / "codex-hooks.json").read_text()) == \
        install.claude_style_hooks("codex", install.CODEX_EVENTS)
    assert json.loads((PLUGIN / "hooks" / "cursor-hooks.json").read_text()) == install.cursor_hooks()
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    cursor = json.loads((PLUGIN / ".cursor-plugin" / "plugin.json").read_text())
    assert codex["hooks"] == "./hooks/codex-hooks.json", "Codex must not read the Claude Code hooks.json"
    assert cursor["hooks"] == "./hooks/cursor-hooks.json"
    for manifest in (codex, cursor):
        assert "mcpServers" not in manifest
        assert "skills" not in manifest
    assert not (PLUGIN / ".mcp.json").exists()

    # Claude exposes one explicit user-only /openreflex dashboard command. It must not
    # become model-invocable or reintroduce the removed default MCP surface.
    skill = (PLUGIN / "skills" / "openreflex" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: openreflex" in skill
    assert "user-invocable: true" in skill
    assert "disable-model-invocation: true" in skill
    assert "launcher.cjs" in skill and "onboard" in skill
    assert "global `openreflex` executable" in skill
    assert "diagnostics" in skill and "Do not enable MCP diagnostics" in skill

    launcher = (PLUGIN / "runtime" / "launcher.cjs").read_text(encoding="utf-8")
    assert "openreflex==" in launcher
    assert "OPENREFLEX_RUNTIME_ROOT" in launcher
    assert "shutil.which" not in launcher
    assert "runtime/launcher.cjs" in json.dumps(claude)
    assert "openreflex hook claude-code" not in json.dumps(claude)


def _run(args, stdin="", env_home=None, cwd=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "OPENREFLEX_HOME": str(env_home)}
    return subprocess.run([sys.executable, "-m", "openreflex", *args], input=stdin.encode(), capture_output=True,
                          env=env, cwd=cwd, timeout=60)


def test_cli_hook_never_blocks_even_with_bad_arguments(isolated_home, project):
    for args in (["hook"], ["hook", "nonsense-agent", "PostToolUse"], ["hook", "claude-code", "PostToolUse"]):
        result = _run(args, stdin="{broken", env_home=isolated_home, cwd=project)
        assert result.returncode == 0, (args, result.stderr)


def test_cli_end_to_end_capture_via_subprocess(isolated_home, project):
    connected = _run(["install", "claude-code", "--project", str(project)], env_home=isolated_home)
    assert connected.returncode == 0, connected.stderr
    assert not (project / ".mcp.json").exists(), "normal capture must not require a model-facing MCP server"
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


@pytest.mark.parametrize("agent", ["claude-code", "codex", "cursor", "opencode"])
def test_diagnostics_mcp_is_explicit_opt_in(project, agent):
    install.install(agent, project)
    changes = install.install_diagnostics(agent, project)
    assert changes
    if agent == "claude-code":
        assert json.loads((project / ".mcp.json").read_text())["mcpServers"]["openreflex"]["args"] == ["mcp"]
    elif agent == "codex":
        text = (project / ".codex/config.toml").read_text()
        assert text.count("[mcp_servers.openreflex]") == 1
        assert 'env_vars = ["OPENREFLEX_HOME"]' in text
    elif agent == "cursor":
        assert json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]["openreflex"]["command"] == "openreflex"
    else:
        assert json.loads((project / "opencode.json").read_text())["mcp"]["openreflex"]["enabled"] is True

    assert install.uninstall_diagnostics(agent, project)
    if agent == "claude-code" and (project / ".mcp.json").exists():
        assert "openreflex" not in json.loads((project / ".mcp.json").read_text()).get("mcpServers", {})
    elif agent == "codex" and (project / ".codex/config.toml").exists():
        assert "[mcp_servers.openreflex]" not in (project / ".codex/config.toml").read_text()
    elif agent == "cursor" and (project / ".cursor/mcp.json").exists():
        assert "openreflex" not in json.loads((project / ".cursor/mcp.json").read_text()).get("mcpServers", {})
    elif agent == "opencode" and (project / "opencode.json").exists():
        assert "openreflex" not in json.loads((project / "opencode.json").read_text()).get("mcp", {})


def test_release_versions_agree():
    import tomllib

    import openreflex
    version = tomllib.loads((PLUGIN.parents[1] / "pyproject.toml").read_text())["project"]["version"]
    server = json.loads((PLUGIN.parents[1] / "server.json").read_text())
    manifests = [json.loads((PLUGIN / folder / "plugin.json").read_text())["version"]
                 for folder in (".claude-plugin", ".codex-plugin", ".cursor-plugin")]
    assert openreflex.__version__ == version
    assert server["version"] == version and [p["version"] for p in server["packages"]] == [version]
    assert manifests == [version] * 3
    assert f"mcp-name: {server['name']}" in (PLUGIN.parents[1] / "README.md").read_text(encoding="utf-8")
