"""Project-level installation for each supported agent. Merges into existing config files idempotently.

Plugin installs (plugins/openreflex) cover Claude Code and Codex without touching the project; these
installers exist for agents or teams that prefer committed project configuration.
"""

import json
import re
from importlib import resources
from pathlib import Path

from .project import approve

HOOK_COMMAND = "openreflex hook {agent} {event}"
CLAUDE_PLUGIN_ROOT = ' --plugin-root "${CLAUDE_PLUGIN_ROOT}"'
CLAUDE_EVENTS = {"SessionStart": 10, "UserPromptSubmit": 10, "PreToolUse": 10, "PostToolUse": 10,
                 "PostToolUseFailure": 10, "PreCompact": 10, "Stop": 15, "SessionEnd": 5}
CODEX_EVENTS = {"SessionStart": 10, "UserPromptSubmit": 10, "PreToolUse": 10, "PostToolUse": 10,
                "PreCompact": 10, "Stop": 15, "SessionEnd": 3}
CURSOR_EVENTS = {"sessionStart": 10, "beforeSubmitPrompt": 10, "preToolUse": 10, "postToolUse": 10,
                 "postToolUseFailure": 10, "preCompact": 10, "stop": 15, "sessionEnd": 5}


def claude_style_hooks(agent: str, events: dict[str, int]) -> dict:
    def command(event: str) -> str:
        base = HOOK_COMMAND.format(agent=agent, event=event)
        return base + CLAUDE_PLUGIN_ROOT if agent == "claude-code" else base

    return {"hooks": {event: [{"hooks": [{"type": "command", "command": command(event),
                                          "timeout": timeout}]}] for event, timeout in events.items()}}


def cursor_hooks() -> dict:
    return {"version": 1, "hooks": {event: [{"command": HOOK_COMMAND.format(agent="cursor", event=event),
                                             "timeout": timeout}] for event, timeout in CURSOR_EVENTS.items()}}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text) if text.strip() else {}
    except ValueError as error:
        raise ValueError(f"{path} is not valid JSON; fix it or remove it before installing") from error


def _ours(entry: object) -> bool:
    return "openreflex hook" in json.dumps(entry)


def _merge_hooks(existing: dict, ours: dict) -> dict:
    merged = dict(existing)
    hooks = {event: [e for e in entries if not _ours(e)] for event, entries in (existing.get("hooks") or {}).items()}
    for event, entries in ours["hooks"].items():
        hooks[event] = hooks.get(event, []) + entries
    merged["hooks"] = {event: entries for event, entries in hooks.items() if entries}
    for key, value in ours.items():
        if key != "hooks":
            merged.setdefault(key, value)
    return merged


def _remove_hooks(existing: dict) -> dict:
    """Remove only OpenReflex hook entries, preserving all user-owned config."""
    merged = dict(existing)
    hooks = {event: [entry for entry in entries if not _ours(entry)]
             for event, entries in (existing.get("hooks") or {}).items()}
    hooks = {event: entries for event, entries in hooks.items() if entries}
    if hooks:
        merged["hooks"] = hooks
    else:
        merged.pop("hooks", None)
    return merged


def _write(path: Path, data: dict | str, dry_run: bool, changes: list[str]) -> None:
    text = data if isinstance(data, str) else json.dumps(data, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    changes.append(str(path))
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _ensure_project_boundary(project: Path, dry_run: bool, changes: list[str]) -> None:
    """Create a non-secret project marker without replacing an existing user-owned marker."""
    marker = project / ".openreflex.json"
    if marker.exists():
        return
    _write(marker, {"version": 1, "scope": "project"}, dry_run, changes)


def _remove_json_key(path: Path, container: str, key: str, dry_run: bool, changes: list[str]) -> None:
    if not path.exists():
        return
    data = _load(path)
    section = data.get(container)
    if not isinstance(section, dict) or key not in section:
        return
    section = dict(section)
    section.pop(key, None)
    if section:
        data[container] = section
    else:
        data.pop(container, None)
    _write(path, data, dry_run, changes)


def install_diagnostics(agent: str, project: Path, dry_run: bool = False) -> list[str]:
    """Opt in to the model-facing MCP diagnostics surface for one project."""
    changes: list[str] = []
    _ensure_project_boundary(project, dry_run, changes)
    if agent == "claude-code":
        mcp = project / ".mcp.json"
        data = _load(mcp)
        data.setdefault("mcpServers", {})["openreflex"] = {"command": "openreflex", "args": ["mcp"]}
        _write(mcp, data, dry_run, changes)
    elif agent == "codex":
        config = project / ".codex" / "config.toml"
        text = config.read_text(encoding="utf-8") if config.exists() else ""
        if not re.search(r"^\[mcp_servers\.openreflex\]", text, re.MULTILINE):
            block = '[mcp_servers.openreflex]\ncommand = "openreflex"\nargs = ["mcp"]\nenv_vars = ["OPENREFLEX_HOME"]\n'
            _write(config, (text.rstrip() + "\n\n" if text.strip() else "") + block, dry_run, changes)
    elif agent == "cursor":
        mcp = project / ".cursor" / "mcp.json"
        data = _load(mcp)
        data.setdefault("mcpServers", {})["openreflex"] = {
            "type": "stdio", "command": "openreflex", "args": ["mcp", "--project", "${workspaceFolder}"]}
        _write(mcp, data, dry_run, changes)
    elif agent == "opencode":
        config_path = next((p for p in (project / "opencode.jsonc", project / "opencode.json") if p.exists()),
                           project / "opencode.json")
        if config_path.suffix == ".jsonc":
            changes.append(f"{config_path} (JSONC not edited; add mcp.openreflex manually)")
        else:
            data = _load(config_path)
            data.setdefault("$schema", "https://opencode.ai/config.json")
            data.setdefault("mcp", {})["openreflex"] = {
                "type": "local", "command": ["openreflex", "mcp"], "enabled": True}
            _write(config_path, data, dry_run, changes)
    else:
        raise ValueError(f"Unsupported agent: {agent}")
    return changes


def uninstall_diagnostics(agent: str, project: Path, dry_run: bool = False) -> list[str]:
    """Remove only the optional MCP diagnostics surface; ambient hooks stay installed."""
    changes: list[str] = []
    if agent == "claude-code":
        _remove_json_key(project / ".mcp.json", "mcpServers", "openreflex", dry_run, changes)
    elif agent == "codex":
        config = project / ".codex" / "config.toml"
        if config.exists():
            text = config.read_text(encoding="utf-8")
            cleaned = re.sub(r"(?ms)^\[mcp_servers\.openreflex\]\n.*?(?=^\[|\Z)", "", text).strip()
            cleaned = cleaned + ("\n" if cleaned else "")
            if cleaned != text:
                _write(config, cleaned, dry_run, changes)
    elif agent == "cursor":
        _remove_json_key(project / ".cursor" / "mcp.json", "mcpServers", "openreflex", dry_run, changes)
    elif agent == "opencode":
        _remove_json_key(project / "opencode.json", "mcp", "openreflex", dry_run, changes)
    else:
        raise ValueError(f"Unsupported agent: {agent}")
    return changes


def install(agent: str, project: Path, dry_run: bool = False) -> list[str]:
    """Install the ambient runtime. Normal operation is hooks-only; MCP diagnostics are opt-in."""
    changes: list[str] = []
    _ensure_project_boundary(project, dry_run, changes)
    if agent == "claude-code":
        settings = project / ".claude" / "settings.json"
        _write(settings, _merge_hooks(_load(settings), claude_style_hooks("claude-code", CLAUDE_EVENTS)), dry_run, changes)
        # Re-running the default installer upgrades pre-0.7 projects to ambient mode.
        changes += uninstall_diagnostics(agent, project, dry_run)
    elif agent == "codex":
        hooks = project / ".codex" / "hooks.json"
        _write(hooks, _merge_hooks(_load(hooks), claude_style_hooks("codex", CODEX_EVENTS)), dry_run, changes)
        changes += uninstall_diagnostics(agent, project, dry_run)
    elif agent == "cursor":
        hooks = project / ".cursor" / "hooks.json"
        existing = _load(hooks)
        merged = _merge_hooks(existing, cursor_hooks())
        merged["version"] = existing.get("version", 1)
        _write(hooks, merged, dry_run, changes)
        changes += uninstall_diagnostics(agent, project, dry_run)
    elif agent == "opencode":
        plugin = resources.files("openreflex").joinpath("integrations/opencode.ts").read_text(encoding="utf-8")
        _write(project / ".opencode" / "plugins" / "openreflex.ts", plugin, dry_run, changes)
        changes += uninstall_diagnostics(agent, project, dry_run)
    else:
        raise ValueError(f"Unsupported agent: {agent}")
    if not dry_run:
        approve(project, source=f"install:{agent}")
    return changes

def uninstall(agent: str, project: Path, dry_run: bool = False) -> list[str]:
    """Remove OpenReflex-owned integration entries without deleting project memory or user config."""
    changes: list[str] = []
    if agent == "claude-code":
        settings = project / ".claude" / "settings.json"
        if settings.exists():
            _write(settings, _remove_hooks(_load(settings)), dry_run, changes)
        _remove_json_key(project / ".mcp.json", "mcpServers", "openreflex", dry_run, changes)
    elif agent == "codex":
        hooks = project / ".codex" / "hooks.json"
        if hooks.exists():
            _write(hooks, _remove_hooks(_load(hooks)), dry_run, changes)
        config = project / ".codex" / "config.toml"
        if config.exists():
            text = config.read_text(encoding="utf-8")
            cleaned = re.sub(r"(?ms)^\[mcp_servers\.openreflex\]\n.*?(?=^\[|\Z)", "", text).strip()
            cleaned = cleaned + ("\n" if cleaned else "")
            if cleaned != text:
                _write(config, cleaned, dry_run, changes)
    elif agent == "cursor":
        hooks = project / ".cursor" / "hooks.json"
        if hooks.exists():
            _write(hooks, _remove_hooks(_load(hooks)), dry_run, changes)
        _remove_json_key(project / ".cursor" / "mcp.json", "mcpServers", "openreflex", dry_run, changes)
    elif agent == "opencode":
        plugin = project / ".opencode" / "plugins" / "openreflex.ts"
        if plugin.exists():
            changes.append(str(plugin))
            if not dry_run:
                plugin.unlink()
        _remove_json_key(project / "opencode.json", "mcp", "openreflex", dry_run, changes)
    else:
        raise ValueError(f"Unsupported agent: {agent}")
    return changes
