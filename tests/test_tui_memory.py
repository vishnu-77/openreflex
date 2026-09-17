import json

from openreflex.claude_ui import configure_statusline, remove_statusline
from openreflex.entrypoint import _stop_state
from openreflex.project_memory import build_snapshot, read_state, update_state
from openreflex.tui import dashboard, statusline


def test_statusline_uses_openreflex_brand_states_and_colours(project):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    build_snapshot(project)
    update_state(project, "reflexing", memory="building")

    line = statusline(project, force_colour=True)

    assert "OpenReflex" in line and "REFLEXING" in line
    assert "\x1b[38;2;40;106;112m" in line
    assert "\x1b[38;2;192;122;44m" in line
    assert "work normally" in line


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


def test_dashboard_is_readable_without_colour(project):
    (project / "Chart.yaml").write_text("apiVersion: v2\nname: demo\n", encoding="utf-8")
    build_snapshot(project)
    update_state(project, "recall", recall={"experiences": 2}, task={"route": "inspect-first"})

    text = dashboard(project, colour=False)

    assert "OPENREFLEX" in text
    assert "PROJECT MEMORY" in text
    assert "EXECUTION MEMORY" in text
    assert "inspect-first" in text
    assert "2 related" in text
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
