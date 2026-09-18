import json

from openreflex import __version__
from openreflex.claude_ui import configure_statusline, remove_statusline
from openreflex.entrypoint import (
    _prompt_state,
    _record_hook_runtime,
    _record_mcp_runtime,
    _stop_state,
    _tool_end_state,
    _tool_start_state,
)
from openreflex.project_memory import build_snapshot, read_state, update_state
from openreflex.tui import dashboard, statusline


def test_statusline_uses_openreflex_brand_states_and_colours(project):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    build_snapshot(project)
    update_state(project, "reflexing", memory="building")

    line = statusline(project, force_colour=True)

    assert "OpenReflex" in line and f"v{__version__}" in line and "REFLEXING" in line
    assert "\x1b[38;2;40;106;112m" in line
    assert "\x1b[38;2;192;122;44m" in line
    assert "work normally" in line


def test_statusline_shows_current_safe_tool_activity(project):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "charts/app/values.yaml"}}

    _tool_start_state(project, payload)
    running = statusline(project, force_colour=False)
    assert "WATCH" in running
    assert "READ charts/app/values.yaml" in running
    assert "0 calls" in running

    _tool_end_state(project, payload)
    completed = statusline(project, force_colour=False)
    assert "last READ charts/app/values.yaml" in completed
    assert "1 calls" in completed


def test_shell_activity_does_not_echo_raw_command(project):
    payload = {"tool_name": "Bash", "tool_input": {"command": "curl https://example.invalid?token=super-secret"}}

    _tool_start_state(project, payload)
    line = statusline(project, force_colour=False)

    assert "RUN" in line
    assert "curl" not in line
    assert "super-secret" not in line


def test_verification_activity_is_explicit(project):
    payload = {"tool_name": "Bash", "tool_input": {"command": "helm lint charts/app"}}

    _tool_start_state(project, payload)
    running = statusline(project, force_colour=False)
    assert "VERIFY" in running
    assert "LINT" in running

    _tool_end_state(project, payload, failed=True)
    failed = statusline(project, force_colour=False)
    assert "last LINT failed" in failed
    assert "1 calls" in failed


def test_new_prompt_resets_previous_task_activity_and_calls(project):
    update_state(project, "watch", execution={"calls": 9}, activity={"label": "READ", "status": "complete"},
                 task={"active": False, "route": "old-route"})

    _prompt_state(project, "", None)
    state = read_state(project)

    assert state["phase"] == "watch"
    assert state["execution"] == {"calls": 0}
    assert state["activity"] == {}
    assert state["task"] == {"active": True, "mode": "build"}


def test_verification_continuation_stays_in_verify_instead_of_remember(project):
    output = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": "OpenReflex cannot verify this changed task yet. Run the relevant check.",
        }
    })

    _stop_state(project, "claude-code", "s1", output)
    state = read_state(project)

    assert state["phase"] == "verify"
    assert state["outcome"] == "verification required"
    assert state["verification"] == "pending"
    assert state["task"]["active"] is True


def test_final_stop_marks_task_inactive(project):
    update_state(project, "watch", task={"active": True, "route": "inspect-first"}, execution={"calls": 3})
    _stop_state(project, "claude-code", "missing", json.dumps({"systemMessage": "↺ OpenReflex · COMPLETE\nsuccess · inspect-first"}))
    state = read_state(project)
    assert state["phase"] == "remember"
    assert state["task"]["active"] is False
    assert state["outcome"] == "success"


def test_hook_runtime_records_plugin_manifest_version_without_cache_path(project, tmp_path):
    plugin = tmp_path / "plugin-cache" / "openreflex"
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "openreflex", "version": __version__}), encoding="utf-8")

    _record_hook_runtime(project, ["hook", "claude-code", "SessionStart", "--plugin-root", str(plugin)])
    state = read_state(project)

    assert state["hook_runtime_version"] == __version__
    assert state["plugin_version"] == __version__
    assert str(plugin) not in json.dumps(state)
    line = statusline(project, force_colour=False)
    assert f"OpenReflex v{__version__}" in line
    assert "VERSION MISMATCH" not in line


def test_mcp_runtime_is_visible_and_version_alignment_is_reported(project, tmp_path):
    plugin = tmp_path / "plugin" / "openreflex"
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "openreflex", "version": __version__}), encoding="utf-8")

    _record_hook_runtime(project, ["hook", "claude-code", "SessionStart", "--plugin-root", str(plugin)])
    _record_mcp_runtime(project)

    text = dashboard(project, colour=False)
    assert "RUNTIME" in text
    assert f"package          v{__version__}" in text
    assert f"Claude plugin    v{__version__}" in text
    assert f"MCP runtime      v{__version__}" in text
    assert "version state    ALIGNED" in text


def test_version_mismatch_is_visible_in_statusline(project, tmp_path):
    plugin = tmp_path / "plugin" / "openreflex"
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "openreflex", "version": "9.9.9"}), encoding="utf-8")

    _record_hook_runtime(project, ["hook", "claude-code", "SessionStart", "--plugin-root", str(plugin)])
    _record_mcp_runtime(project)

    line = statusline(project, force_colour=False)
    assert "VERSION MISMATCH" in line
    assert "plugin v9.9.9" in line
    assert f"runtime v{__version__}" in line


def test_dashboard_is_readable_without_colour(project):
    (project / "Chart.yaml").write_text("apiVersion: v2\nname: demo\n", encoding="utf-8")
    build_snapshot(project)
    update_state(project, "recall", recall={"experiences": 2}, task={"route": "inspect-first", "active": True},
                 activity={"label": "SEARCH", "status": "running"})

    text = dashboard(project, colour=False)

    assert "OPENREFLEX" in text
    assert f"v{__version__}" in text
    assert "RUNTIME" in text
    assert "PROJECT MEMORY" in text
    assert "EXECUTION MEMORY" in text
    assert "inspect-first" in text
    assert "2 related" in text
    assert "activity         SEARCH" in text
    assert "\x1b[" not in text


def test_claude_statusline_is_added_only_when_user_has_none(project):
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"hooks": {}}\n', encoding="utf-8")

    assert configure_statusline(project) == "configured"
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["statusLine"]["command"] == "openreflex statusline"
    assert data["statusLine"]["refreshInterval"] == 2
    assert remove_statusline(project) is True
    assert "statusLine" not in json.loads(settings.read_text(encoding="utf-8"))


def test_existing_user_statusline_is_never_replaced_or_removed(project):
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    original = {"statusLine": {"type": "command", "command": "~/my-status.sh"}, "hooks": {}}
    settings.write_text(json.dumps(original), encoding="utf-8")

    assert configure_statusline(project) == "preserved-existing"
    assert json.loads(settings.read_text(encoding="utf-8"))["statusLine"] == original["statusLine"]
    assert remove_statusline(project) is False
    assert json.loads(settings.read_text(encoding="utf-8"))["statusLine"] == original["statusLine"]
