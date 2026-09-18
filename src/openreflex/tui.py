"""Low-latency presentation layer for OpenReflex state.

The TUI/statusline never scans a repository or queries the learning engine just to
paint the screen. It only reads cached state + project-memory snapshots.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import __version__
from .project_memory import load_snapshot, read_state

TEAL = "\x1b[38;2;40;106;112m"
AMBER = "\x1b[38;2;192;122;44m"
MUTED = "\x1b[38;2;120;120;120m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
AMBER_PHASES = {"reflexing", "refreshing", "verify", "waiting", "pivot", "stale", "cold"}


def _colour_enabled(force: bool = False) -> bool:
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return False
    return force or bool(getattr(sys.stdout, "isatty", lambda: False)())


def _paint(text: str, colour: str, enabled: bool, bold: bool = False) -> str:
    if not enabled:
        return text
    return f"{BOLD if bold else ''}{colour}{text}{RESET}"


def _display_phase(state: dict) -> str:
    phase = str(state.get("phase") or "cold").lower()
    changed = float(state.get("phase_changed_at") or 0)
    age = time.time() - changed if changed else 0
    task = state.get("task") or {}
    # RECALL is a brief retrieval moment, not a long-running state. Once the recap window passes,
    # an active task is being watched; only a closed task should look READY.
    if phase == "recall" and changed and age > 4:
        if not task.get("active"):
            return "ready"
        mode = str(task.get("mode") or "build")
        return "investigate" if mode == "investigate" else "think" if mode == "think" else "watch"
    if phase == "remember" and changed and age > 6:
        return "ready"
    return phase


def _activity_text(state: dict, *, include_last: bool = True) -> str | None:
    activity = state.get("activity") or {}
    label = str(activity.get("label") or "").strip()
    if not label:
        return None
    target = str(activity.get("target") or "").strip()
    status = str(activity.get("status") or "").lower()
    prefix = ""
    if include_last and status in {"complete", "failed"}:
        prefix = "last "
    text = f"{prefix}{label}"
    if target:
        text += f" {target}"
    if status == "failed":
        text += " failed"
    return text


def _version_state(state: dict) -> tuple[str, str | None, str | None, bool]:
    runtime = str(state.get("hook_runtime_version") or __version__)
    plugin = str(state.get("plugin_version") or "").strip() or None
    mcp = str(state.get("mcp_runtime_version") or "").strip() or None
    compared = [value for value in (plugin, mcp) if value]
    aligned = all(value == runtime for value in compared)
    return runtime, plugin, mcp, aligned


def statusline(project: Path, *, force_colour: bool = True) -> str:
    state, snapshot = read_state(project), load_snapshot(project)
    enabled = _colour_enabled(force_colour)
    phase = _display_phase(state)
    runtime, plugin, mcp, aligned = _version_state(state)
    phase_colour = AMBER if phase in AMBER_PHASES else TEAL
    brand = _paint(f"↺ OpenReflex v{runtime}", TEAL, enabled, bold=True)
    status = _paint(phase.upper(), phase_colour, enabled, bold=True)
    details: list[str] = []
    execution = state.get("execution") or {}
    activity = _activity_text(state)
    usage = state.get("token_usage") or {}
    total_tokens = sum(int(usage.get(key, 0) or 0) for key in ("input", "output", "cache_read", "cache_creation"))

    if phase == "reflexing":
        details.append("understanding project · work normally")
    elif phase == "refreshing":
        details.append("project changed · memory refreshing")
    elif phase == "recall":
        recall = state.get("recall") or {}
        if recall.get("experiences") is not None:
            details.append(f"{recall.get('experiences', 0)} related")
        route = (state.get("task") or {}).get("route")
        if route:
            details.append(str(route))
    elif phase in {"watch", "investigate", "think"}:
        if activity:
            details.append(activity)
        elif phase == "investigate":
            details.append("researching")
        elif phase == "think":
            details.append("reasoning")
        if execution.get("calls") is not None:
            details.append(f"{execution.get('calls', 0)} calls")
        if total_tokens:
            details.append(f"{total_tokens / 1000:.1f}k tokens")
        if phase == "watch" and execution.get("budget_used") is not None:
            details.append(f"budget {float(execution['budget_used']):.0%}")
    elif phase == "waiting":
        pending = state.get("pending") or {}
        if pending.get("background"):
            details.append(f"{pending['background']} background")
        if pending.get("scheduled"):
            details.append(f"{pending['scheduled']} scheduled")
        if not details:
            details.append("work still scheduled")
    elif phase == "verify":
        if activity:
            details.append(activity)
        else:
            details.append(str(state.get("verification") or "closing outcome"))
        if execution.get("calls") is not None:
            details.append(f"{execution.get('calls', 0)} calls")
    elif phase == "remember":
        details.append(str(state.get("outcome") or "experience retained"))
        if execution.get("calls") is not None:
            details.append(f"{execution.get('calls', 0)} calls")
        if total_tokens:
            details.append(f"{total_tokens / 1000:.1f}k tokens")
    else:
        facts = state.get("facts", sum(f.get("state") == "active" for f in snapshot.get("facts", [])))
        experiences = state.get("experiences")
        verified = state.get("verified")
        map_files = state.get("map_files")
        if facts:
            details.append(f"{facts} facts")
        if map_files:
            details.append(f"{map_files} indexed")
        if experiences is not None:
            details.append(f"{experiences} experiences")
        if verified is not None:
            details.append(f"{verified} verified")
        if not details:
            details.append("memory active" if snapshot else "memory warming")

    loaded_at = float(state.get("mcp_loaded_at") or 0)
    if mcp and loaded_at and time.time() - loaded_at < 8:
        details.insert(0, f"MCP loaded v{mcp}")

    muted = _paint(" · ".join(details), MUTED, enabled)
    line = f"{brand}  {status}  {project.name}" + (f" · {muted}" if muted else "")
    if not aligned:
        versions = [f"plugin v{plugin}" if plugin else None, f"MCP v{mcp}" if mcp else None,
                    f"runtime v{runtime}"]
        warning = "VERSION MISMATCH · " + " · ".join(item for item in versions if item)
        line += " · " + _paint(warning, AMBER, enabled, bold=True)
    return line


def dashboard(project: Path, *, colour: bool | None = None) -> str:
    state, snapshot = read_state(project), load_snapshot(project)
    enabled = _colour_enabled() if colour is None else colour
    phase = _display_phase(state)
    runtime, plugin, mcp, aligned = _version_state(state)
    header = f"{_paint('OPENREFLEX v' + runtime, TEAL, enabled, bold=True)}{' ' * 8}{_paint('↺ ' + phase.upper(), AMBER if phase in AMBER_PHASES else TEAL, enabled, bold=True)}"
    facts = snapshot.get("facts", [])
    active = sum(f.get("state") == "active" for f in facts)
    stale = sum(f.get("state") == "stale" for f in facts)
    task = state.get("task") or {}
    execution = state.get("execution") or {}
    recall = state.get("recall") or {}
    project_map = snapshot.get("project_map") or {}
    indexed = snapshot.get("indexed_files", [])
    symbol_files = sum(bool(item.get("symbols")) for item in indexed)
    dependencies = project_map.get("dependencies", [])
    relationships = project_map.get("relationships", [])
    hotspots = project_map.get("hotspots", [])[:3]
    activity = _activity_text(state)
    usage = state.get("token_usage") or {}
    total_tokens = sum(int(usage.get(key, 0) or 0) for key in ("input", "output", "cache_read", "cache_creation"))

    version_status = "ALIGNED" if aligned else "MISMATCH"
    lines = [header, "", project.name, "─" * 58, "", "RUNTIME",
             f"  package          v{runtime}",
             f"  Claude plugin    {'v' + plugin if plugin else '-'}",
             f"  MCP runtime      {'v' + mcp if mcp else '-'}",
             f"  version state    {version_status}",
             "", "PROJECT MEMORY",
             f"  type             {snapshot.get('project_kind', 'warming')}",
             f"  indexed files    {len(indexed)}",
             f"  facts            {active} active / {stale} stale",
             f"  generation       {snapshot.get('generation', 0)}"]

    if project_map:
        lines += ["", "PROJECT MAP",
                  f"  tracked files    {project_map.get('tracked_files', 0)}",
                  f"  symbol files     {symbol_files}",
                  f"  dependencies     {len(dependencies)}",
                  f"  co-change edges  {len(relationships)}"]
        if hotspots:
            lines.append("  hotspots         " + " · ".join(
                f"{item.get('path')} ({item.get('changes', 0)})" for item in hotspots
            ))

    lines += ["", "EXECUTION MEMORY",
              f"  experiences      {state.get('experiences', 0)}",
              f"  known outcomes   {state.get('known_outcomes', 0)}",
              f"  verified         {state.get('verified', 0)}",
              f"  lessons          {state.get('lessons', 0)}",
              "", "CURRENT REFLEX",
              f"  phase            {phase.upper()}",
              f"  mode             {str(task.get('mode') or 'build').upper()}",
              f"  suggested path   {task.get('route') or '-'}",
              f"  recall           {recall.get('experiences', 0)} related",
              f"  activity         {activity or '-'}",
              f"  calls            {execution.get('calls', 0)}",
              f"  budget           {float(execution.get('budget_used', 0)):.0%}"]
    lines += ["", "TOKEN USAGE",
              f"  tracking         {state.get('token_tracking', 'off')}",
              f"  input            {int(usage.get('input', 0) or 0):,}",
              f"  output           {int(usage.get('output', 0) or 0):,}",
              f"  cache read       {int(usage.get('cache_read', 0) or 0):,}",
              f"  cache creation   {int(usage.get('cache_creation', 0) or 0):,}",
              f"  total            {total_tokens:,}",
              f"  requests         {int(usage.get('requests', 0) or 0)}",
              f"  est. cost        ${float(usage.get('cost_usd', 0) or 0):.4f}"]
    commands = [item.get("command") for item in snapshot.get("commands", []) if item.get("state") == "active"][:5]
    if commands:
        lines += ["", "VERIFICATION", "  " + " · ".join(str(item) for item in commands)]
    lines += ["", _paint("Project-map signals are structural priors; verified outcomes remain separate evidence.", MUTED, enabled)]
    return "\n".join(lines)


def claude_project_from_stdin(raw: str) -> str | None:
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    value = workspace.get("project_dir") or workspace.get("current_dir") or payload.get("cwd")
    return value if isinstance(value, str) and value else None
