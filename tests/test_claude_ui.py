import json

import pytest

from openreflex import __version__
from openreflex.claude_ui import (
    configure_statusline,
    remove_project_integration,
    remove_orphaned_statusline,
    remove_project_statusline,
    remove_statusline,
)


def _user_settings(tmp_path, monkeypatch):
    config = tmp_path / "claude-user"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return config / "settings.json"


def test_statusline_is_user_scoped_and_does_not_create_project_settings(tmp_path, monkeypatch):
    settings = _user_settings(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    runtime = tmp_path / ".openreflex" / "runtime" / f"v{__version__}" / "bin" / "openreflex"
    monkeypatch.setenv("OPENREFLEX_RUNTIME_COMMAND", f'"{runtime}"')

    assert configure_statusline(project) == "configured"

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["statusLine"]["command"].endswith(" statusline")
    assert f"/runtime/v{__version__}/" in data["statusLine"]["command"].replace("\\", "/")
    assert not (project / ".claude" / "settings.json").exists()


def test_configure_migrates_legacy_project_statusline_without_touching_other_settings(tmp_path, monkeypatch):
    user_settings = _user_settings(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project_settings = project / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True)
    project_settings.write_text(json.dumps({
        "permissions": {"allow": ["Bash(git status)"]},
        "statusLine": {"type": "command", "command": "openreflex statusline"},
    }), encoding="utf-8")

    assert configure_statusline(project) == "configured"

    migrated = json.loads(project_settings.read_text(encoding="utf-8"))
    assert migrated == {"permissions": {"allow": ["Bash(git status)"]}}
    assert "statusLine" in json.loads(user_settings.read_text(encoding="utf-8"))


def test_configure_removes_statusline_only_project_file_entirely(tmp_path, monkeypatch):
    _user_settings(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project_settings = project / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True)
    project_settings.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "openreflex statusline"},
    }), encoding="utf-8")

    configure_statusline(project)

    assert not project_settings.exists()
    assert not project_settings.parent.exists()


def test_existing_user_statusline_is_preserved(tmp_path, monkeypatch):
    settings = _user_settings(tmp_path, monkeypatch)
    settings.parent.mkdir(parents=True)
    original = {
        "theme": "dark",
        "statusLine": {"type": "command", "command": "~/.claude/my-statusline.sh", "padding": 1},
    }
    settings.write_text(json.dumps(original), encoding="utf-8")

    assert configure_statusline(tmp_path / "repo") == "preserved-existing"
    assert json.loads(settings.read_text(encoding="utf-8")) == original


def test_invalid_user_settings_are_never_overwritten(tmp_path, monkeypatch):
    settings = _user_settings(tmp_path, monkeypatch)
    settings.parent.mkdir(parents=True)
    settings.write_text("{broken", encoding="utf-8")

    assert configure_statusline(tmp_path / "repo") == "preserved-invalid"
    assert settings.read_text(encoding="utf-8") == "{broken"


def test_project_cleanup_never_removes_user_statusline(tmp_path, monkeypatch):
    settings = _user_settings(tmp_path, monkeypatch)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "openreflex statusline"},
    }), encoding="utf-8")

    project = tmp_path / "repo"
    project_settings = project / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True)
    project_settings.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "openreflex statusline"},
    }), encoding="utf-8")

    assert remove_project_statusline(project) is True
    assert not project_settings.exists()
    assert settings.exists()
    assert remove_statusline() is True
    assert json.loads(settings.read_text(encoding="utf-8")) == {}


def test_project_cleanup_removes_legacy_openreflex_hooks_and_preserves_user_hooks(tmp_path, monkeypatch):
    _user_settings(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project_settings = project / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True)
    user_hook = {"hooks": [{"type": "command", "command": "echo user-owned"}]}
    openreflex_hook = {
        "hooks": [{
            "type": "command",
            "command": 'openreflex hook claude-code Stop --plugin-root "${CLAUDE_PLUGIN_ROOT}"',
            "timeout": 15,
        }]
    }
    project_settings.write_text(json.dumps({
        "permissions": {"allow": ["Bash(git status)"]},
        "hooks": {"Stop": [user_hook, openreflex_hook]},
    }), encoding="utf-8")

    assert remove_project_integration(project) is True

    data = json.loads(project_settings.read_text(encoding="utf-8"))
    assert data["permissions"] == {"allow": ["Bash(git status)"]}
    assert data["hooks"]["Stop"] == [user_hook]


def test_project_cleanup_deletes_openreflex_only_hook_file(tmp_path, monkeypatch):
    _user_settings(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project_settings = project / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True)
    project_settings.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{
                "hooks": [{
                    "type": "command",
                    "command": 'openreflex hook claude-code SessionStart --plugin-root "${CLAUDE_PLUGIN_ROOT}"',
                    "timeout": 10,
                }]
            }]
        }
    }), encoding="utf-8")

    assert remove_project_integration(project) is True
    assert not project_settings.exists()
    assert not project_settings.parent.exists()


def _plugin_statusline(tmp_path, monkeypatch, installed):
    settings = _user_settings(tmp_path, monkeypatch)
    runtime = tmp_path / ".openreflex" / "runtime" / f"v{__version__}" / "bin" / "openreflex"
    monkeypatch.setenv("OPENREFLEX_RUNTIME_COMMAND", f'"{runtime}"')
    assert configure_statusline() == "configured"
    registry = settings.parent / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"version": 2, "plugins": installed}), encoding="utf-8")
    return settings


def test_statusline_removes_itself_after_plugin_uninstall(tmp_path, monkeypatch):
    settings = _plugin_statusline(tmp_path, monkeypatch, {"other@market": []})
    data = json.loads(settings.read_text(encoding="utf-8"))
    settings.write_text(json.dumps({**data, "theme": "dark"}), encoding="utf-8")

    assert remove_orphaned_statusline() is True
    assert json.loads(settings.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_statusline_kept_while_plugin_installed_or_registry_unknown(tmp_path, monkeypatch):
    settings = _plugin_statusline(tmp_path, monkeypatch, {"openreflex@openreflex": []})
    assert remove_orphaned_statusline() is False

    (settings.parent / "plugins" / "installed_plugins.json").unlink()
    assert remove_orphaned_statusline() is False
    assert "statusLine" in json.loads(settings.read_text(encoding="utf-8"))


def test_orphan_cleanup_leaves_standalone_and_user_statuslines(tmp_path, monkeypatch):
    settings = _plugin_statusline(tmp_path, monkeypatch, {})
    for command in ("openreflex statusline", "my-own-statusline"):
        settings.write_text(json.dumps({"statusLine": {"type": "command", "command": command}}), encoding="utf-8")
        assert remove_orphaned_statusline() is False
        assert json.loads(settings.read_text(encoding="utf-8"))["statusLine"]["command"] == command


@pytest.mark.parametrize("variable, runtime_root", [
    ("OPENREFLEX_RUNTIME_ROOT", "custom-runtimes"),
    ("OPENREFLEX_HOME", "custom-home/runtime"),
])
def test_relocated_runtime_statusline_is_cleaned_up(tmp_path, monkeypatch, variable, runtime_root):
    settings = _user_settings(tmp_path, monkeypatch)
    monkeypatch.setenv(variable, str(tmp_path / runtime_root.removesuffix("/runtime")))
    runtime = tmp_path / runtime_root / f"v{__version__}" / "bin" / "openreflex"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"statusLine": {"type": "command", "command": f'"{runtime}" statusline'}}),
                        encoding="utf-8")
    registry = settings.parent / "plugins" / "installed_plugins.json"
    registry.parent.mkdir()
    registry.write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")

    assert remove_orphaned_statusline() is True
    assert "statusLine" not in json.loads(settings.read_text(encoding="utf-8"))
