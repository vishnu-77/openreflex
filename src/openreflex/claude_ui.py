"""Claude Code presentation integration.

OpenReflex owns a user-level status line, never a project-level statusLine entry.
Legacy OpenReflex project entries are migrated away without touching user-owned settings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .project import home

LEGACY_STATUSLINE_COMMAND = "openreflex statusline"


def statusline_command() -> str:
    """Return the runtime-owned statusline command.

    Plugin-managed runtimes pass OPENREFLEX_RUNTIME_COMMAND so the status line cannot
    resolve an unrelated or stale global `openreflex` executable from PATH.
    """
    runtime = os.environ.get("OPENREFLEX_RUNTIME_COMMAND", "").strip()
    return f"{runtime} statusline" if runtime else LEGACY_STATUSLINE_COMMAND


def claude_settings_path() -> Path:
    """Return Claude Code's user-level settings path.

    CLAUDE_CONFIG_DIR is respected so alternate Claude profiles and isolated tests do
    not fall back to the real user home directory.
    """
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".claude"
    return root / "settings.json"


def _runtime_root() -> str:
    """Mirror runtime/launcher.cjs so relocated runtimes are still recognised as ours."""
    root = os.environ.get("OPENREFLEX_RUNTIME_ROOT") or str(home() / "runtime")
    return root.replace("\\", "/").rstrip("/").lower() + "/"


def _runtime_managed(command: object) -> bool:
    if not isinstance(command, str):
        return False
    value = command.replace("\\", "/").lower()
    return (".openreflex/runtime/" in value or _runtime_root() in value) and value.rstrip().endswith(" statusline")


def _ours(command: object) -> bool:
    return command == LEGACY_STATUSLINE_COMMAND or _runtime_managed(command)


def _owned_project_hook(entry: object) -> bool:
    """True only for hook entries installed by OpenReflex into project settings."""
    value = json.dumps(entry, default=str).replace("\\\\", "/").lower()
    return (
        "openreflex hook claude-code" in value
        or ("runtime/launcher.cjs" in value and " hook claude-code " in value)
    )


def _load(path: Path) -> dict | None:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _remove_owned_statusline(path: Path, *, delete_empty: bool = False) -> bool:
    data = _load(path)
    if data is None:
        return False
    current = data.get("statusLine")
    if not isinstance(current, dict) or not _ours(current.get("command")):
        return False

    data.pop("statusLine", None)
    if delete_empty and not data:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        try:
            path.parent.rmdir()
        except OSError:
            pass
    else:
        _write(path, data)
    return True


def remove_project_integration(project: Path) -> bool:
    """Remove legacy OpenReflex-owned Claude project config, preserving user config.

    The Claude plugin is user-scoped and must not require repository-local Claude
    settings. Older OpenReflex releases could leave a project statusLine or hook entries
    behind; remove only those entries and delete the file/directory when it becomes empty.
    """
    path = project / ".claude" / "settings.json"
    data = _load(path)
    if data is None or not path.exists():
        return False

    changed = False
    current = data.get("statusLine")
    if isinstance(current, dict) and _ours(current.get("command")):
        data.pop("statusLine", None)
        changed = True

    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        cleaned = {}
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                cleaned[event] = entries
                continue
            kept = [entry for entry in entries if not _owned_project_hook(entry)]
            if kept:
                cleaned[event] = kept
            if len(kept) != len(entries):
                changed = True
        if cleaned:
            data["hooks"] = cleaned
        elif "hooks" in data:
            data.pop("hooks", None)

    if not changed:
        return False

    if not data:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        try:
            path.parent.rmdir()
        except OSError:
            pass
    else:
        _write(path, data)
    return True


def remove_project_statusline(project: Path) -> bool:
    """Backward-compatible cleanup entry point for legacy callers."""
    return remove_project_integration(project)


def configure_statusline(project: Path | None = None) -> str:
    """Configure the OpenReflex status line in Claude's user settings.

    A project argument is accepted because session hooks know the active project. It is
    used only to migrate a legacy OpenReflex-owned project statusLine entry; the desired
    status line is always written to the user scope.
    """
    if project is not None:
        remove_project_integration(project)

    path = claude_settings_path()
    data = _load(path)
    if data is None:
        return "preserved-invalid"

    existing = data.get("statusLine")
    desired = statusline_command()
    if isinstance(existing, dict):
        current = existing.get("command")
        if current == desired:
            return "already-configured"
        if not _ours(current):
            return "preserved-existing"
        data["statusLine"] = {**existing, "command": desired, "padding": 0, "refreshInterval": 2}
        _write(path, data)
        return "updated-runtime"

    data["statusLine"] = {"type": "command", "command": desired, "padding": 0, "refreshInterval": 2}
    _write(path, data)
    return "configured"


def remove_statusline() -> bool:
    """Remove only the OpenReflex-owned user-level status line."""
    return _remove_owned_statusline(claude_settings_path())


def plugin_installed() -> bool | None:
    """Whether Claude lists an OpenReflex plugin in any scope; None when that is unknown."""
    data = _load(claude_settings_path().parent / "plugins" / "installed_plugins.json")
    plugins = data.get("plugins") if data else None
    if not isinstance(plugins, dict):
        return None
    return any(str(name).lower().startswith("openreflex@") for name in plugins)


def remove_orphaned_statusline() -> bool:
    """Remove the plugin's user status line once the plugin itself is gone.

    Claude Code runs no plugin hook on uninstall, so the status line command is the only
    OpenReflex code that still executes afterwards. Only the runtime-managed command is
    touched: the plugin writes it, whereas the legacy command belongs to standalone installs.
    """
    path = claude_settings_path()
    data = _load(path)
    current = data.get("statusLine") if data else None
    if not isinstance(current, dict) or not _runtime_managed(current.get("command")):
        return False
    if plugin_installed() is not False:
        return False
    return _remove_owned_statusline(path)
