"""Claude Code presentation integration.

OpenReflex owns a user-level status line, never a project-level statusLine entry.
Legacy OpenReflex project entries are migrated away without touching user-owned settings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def _ours(command: object) -> bool:
    if not isinstance(command, str):
        return False
    value = command.replace("\\", "/").lower()
    return command == LEGACY_STATUSLINE_COMMAND or (
        ".openreflex/runtime/" in value and value.rstrip().endswith(" statusline")
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


def remove_project_statusline(project: Path) -> bool:
    """Remove only a legacy OpenReflex project-scoped status line.

    This is a migration/cleanup operation. It never removes a custom project status line
    and never changes the user-level OpenReflex status line.
    """
    return _remove_owned_statusline(project / ".claude" / "settings.json", delete_empty=True)


def configure_statusline(project: Path | None = None) -> str:
    """Configure the OpenReflex status line in Claude's user settings.

    A project argument is accepted because session hooks know the active project. It is
    used only to migrate a legacy OpenReflex-owned project statusLine entry; the desired
    status line is always written to the user scope.
    """
    if project is not None:
        remove_project_statusline(project)

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
