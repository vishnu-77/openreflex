"""Claude Code presentation integration.

OpenReflex only installs its status line when the project has no existing custom
statusLine. A user-owned status line is never replaced.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATUSLINE_COMMAND = "openreflex statusline"


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
    if isinstance(existing, dict):
        if existing.get("command") == STATUSLINE_COMMAND:
            return "already-configured"
        return "preserved-existing"
    data["statusLine"] = {"type": "command", "command": STATUSLINE_COMMAND, "padding": 0, "refreshInterval": 2}
    _write(path, data)
    return "configured"


def remove_statusline(project: Path) -> bool:
    path = project / ".claude" / "settings.json"
    data = _load(path)
    current = data.get("statusLine")
    if not isinstance(current, dict) or current.get("command") != STATUSLINE_COMMAND:
        return False
    data.pop("statusLine", None)
    _write(path, data)
    return True
