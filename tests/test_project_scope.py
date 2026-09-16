import json
import sys

from openreflex import hooks, install
from openreflex.project import approve, home, project_root


def test_install_creates_nested_project_boundary(tmp_path):
    parent = tmp_path / "personal"
    (parent / ".git").mkdir(parents=True)
    nested = parent / "loopsmith"
    nested.mkdir()

    install.install("claude-code", nested)

    marker = nested / ".openreflex.json"
    assert json.loads(marker.read_text()) == {"version": 1, "scope": "project"}
    assert project_root(nested / "src") == nested


def test_install_preserves_existing_project_boundary(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    marker = project / ".openreflex.json"
    marker.write_text('{"owner":"user","custom":true}\n', encoding="utf-8")

    install.install("claude-code", project)

    assert marker.read_text(encoding="utf-8") == '{"owner":"user","custom":true}\n'


def test_hook_trace_contains_real_session(project, monkeypatch):
    approve(project)
    monkeypatch.setattr(sys, "argv", ["openreflex", "hook", "claude-code", "UserPromptSubmit"])

    hooks.handle(
        "claude-code",
        "UserPromptSubmit",
        {
            "session_id": "session-123",
            "cwd": str(project),
            "prompt": "Investigate the authentication redirect regression and verify the likely fix",
        },
    )

    lines = (home() / "logs" / "hooks.log").read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[-1].split(" ", 1)[1])
    assert payload["session"] == "session-123"
    assert payload["project"] == str(project)
    assert payload["event"] == "UserPromptSubmit"
