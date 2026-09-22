"""Claude Code presentation integration.

OpenReflex only installs its status line when the project has no existing custom
statusLine. A user-owned status line is never replaced.
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


def _ours(command: object) -> bool:
    if not isinstance(command, str):
        return False
    value = command.replace("\\", "/").lower()
    return command == LEGACY_STATUSLINE_COMMAND or (
        ".openreflex/runtime/" in value and value.rstrip().endswith(" statusline")
    )


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def configure_statusline(project: Path) -> str:
    path = project / ".claude" / "settings.json"
    data = _load(path)
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


def remove_statusline(project: Path) -> bool:
    path = project / ".claude" / "settings.json"
    data = _load(path)
    current = data.get("statusLine")
    if not isinstance(current, dict) or not _ours(current.get("command")):
        return False
    data.pop("statusLine", None)
    _write(path, data)
    return True
