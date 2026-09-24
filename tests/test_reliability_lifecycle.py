import json
import sys
from pathlib import Path

from openreflex.cli import _claude_plugin_enabled, build_parser
from openreflex.install import uninstall
from openreflex.project import home, project_resolution, project_root


def test_hook_cwd_beats_claude_parent_hint(tmp_path, monkeypatch):
    parent = tmp_path / "workspace"
    repo = parent / "repo"
    (repo / ".git").mkdir(parents=True)
    child = repo / "src"
    child.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(parent))

    assert project_root(child) == repo
    resolution = project_resolution(child)
    assert resolution["source"] == "hook-cwd/git-root"
    assert resolution["agent_hint"] == str(parent)


def test_openreflex_project_remains_authoritative(tmp_path, monkeypatch):
    override = tmp_path / "chosen"
    override.mkdir()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("OPENREFLEX_PROJECT", str(override))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert project_root(repo) == override
    assert project_resolution(repo)["source"] == "OPENREFLEX_PROJECT"


def test_real_hook_process_creates_resolution_trace(project, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["openreflex", "hook", "claude-code", "SessionStart"])
    project_root(project)

    trace = home() / "logs" / "hooks.log"
    assert trace.exists()
    text = trace.read_text(encoding="utf-8")
    assert '"agent":"claude-code"' in text
    assert '"source":"hook-cwd/git-root"' in text
    assert "prompt" not in text and "tool_input" not in text


def test_non_hook_resolution_does_not_fake_hook_health(project, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["openreflex", "doctor", "--project", str(project)])
    project_root(project)
    assert not (home() / "logs" / "hooks.log").exists()


def test_uninstall_claude_preserves_user_hooks_and_other_mcp(project):
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls)"]},
        "hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "echo mine"}]},
            {"hooks": [{"type": "command", "command": "openreflex hook claude-code Stop"}]},
        ]},
    }))
    mcp = project / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {
        "openreflex": {"command": "openreflex", "args": ["mcp"]},
        "other": {"command": "other"},
    }}))

    changes = uninstall("claude-code", project)
    assert len(changes) == 2
    after = json.loads(settings.read_text())
    assert after["permissions"] == {"allow": ["Bash(ls)"]}
    assert len(after["hooks"]["Stop"]) == 1
    assert "echo mine" in json.dumps(after)
    mcp_after = json.loads(mcp.read_text())
    assert "openreflex" not in mcp_after["mcpServers"]
    assert "other" in mcp_after["mcpServers"]


def test_uninstall_codex_removes_only_openreflex_block(project):
    config = project / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[general]\nfoo = "bar"\n\n'
        '[mcp_servers.openreflex]\ncommand = "openreflex"\nargs = ["mcp"]\n\n'
        '[mcp_servers.other]\ncommand = "other"\n'
    )

    uninstall("codex", project)
    text = config.read_text()
    assert "mcp_servers.openreflex" not in text
    assert '[general]' in text
    assert '[mcp_servers.other]' in text


def test_claude_global_plugin_is_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"enabledPlugins": {"openreflex@openreflex": True}}))
    assert _claude_plugin_enabled() is True


def test_cli_exposes_uninstall_command():
    args = build_parser().parse_args(["uninstall", "claude-code", "--dry-run"])
    assert args.agent == "claude-code"
    assert args.dry_run is True
