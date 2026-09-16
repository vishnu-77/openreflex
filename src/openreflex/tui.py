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

from .project_memory import load_snapshot, read_state

TEAL = "\x1b[38;2;40;106;112m"
AMBER = "\x1b[38;2;192;122;44m"
MUTED = "\x1b[38;2;120;120;120m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
AMBER_PHASES = {"reflexing", "refreshing", "verify", "pivot", "stale", "cold"}


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
    if phase in {"remember", "recall"} and changed and time.time() - changed > 6:
        return "ready"
    return phase


def statusline(project: Path, *, force_colour: bool = True) -> str:
    state, snapshot = read_state(project), load_snapshot(project)
    enabled = _colour_enabled(force_colour)
    phase = _display_phase(state)
    phase_colour = AMBER if phase in AMBER_PHASES else TEAL
    brand = _paint("↺ OpenReflex", TEAL, enabled, bold=True)
    status = _paint(phase.upper(), phase_colour, enabled, bold=True)
    details: list[str] = []
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
    elif phase == "watch":
        execution = state.get("execution") or {}
        if execution.get("calls") is not None:
            details.append(f"{execution.get('calls', 0)} calls")
        if execution.get("budget_used") is not None:
            details.append(f"budget {float(execution['budget_used']):.0%}")
    elif phase == "verify":
        details.append(str(state.get("verification") or "closing outcome"))
    elif phase == "remember":
        details.append(str(state.get("outcome") or "experience retained"))
    else:
        facts = state.get("facts", sum(f.get("state") == "active" for f in snapshot.get("facts", [])))
        experiences = state.get("experiences")
        verified = state.get("verified")
        if facts:
            details.append(f"{facts} facts")
        if experiences is not None:
            details.append(f"{experiences} experiences")
        if verified is not None:
            details.append(f"{verified} verified")
        if not details:
            details.append("memory active" if snapshot else "memory warming")
    muted = _paint(" · ".join(details), MUTED, enabled)
    return f"{brand}  {status}  {project.name}" + (f" · {muted}" if muted else "")


def dashboard(project: Path, *, colour: bool | None = None) -> str:
    state, snapshot = read_state(project), load_snapshot(project)
    enabled = _colour_enabled() if colour is None else colour
    phase = _display_phase(state)
    header = f"{_paint('OPENREFLEX', TEAL, enabled, bold=True)}{' ' * 8}{_paint('↺ ' + phase.upper(), AMBER if phase in AMBER_PHASES else TEAL, enabled, bold=True)}"
    facts = snapshot.get("facts", [])
    active = sum(f.get("state") == "active" for f in facts)
    stale = sum(f.get("state") == "stale" for f in facts)
    task = state.get("task") or {}
    execution = state.get("execution") or {}
    recall = state.get("recall") or {}
    lines = [header, "", project.name, "─" * 58, "", "PROJECT MEMORY",
             f"  type             {snapshot.get('project_kind', 'warming')}",
             f"  indexed files    {len(snapshot.get('indexed_files', []))}",
             f"  facts            {active} active / {stale} stale",
             f"  generation       {snapshot.get('generation', 0)}",
             "", "EXECUTION MEMORY",
             f"  experiences      {state.get('experiences', 0)}",
             f"  verified         {state.get('verified', 0)}",
             "", "CURRENT REFLEX",
             f"  phase            {phase.upper()}",
             f"  route            {task.get('route') or '-'}",
             f"  recall           {recall.get('experiences', 0)} related",
             f"  calls            {execution.get('calls', 0)}",
             f"  budget           {float(execution.get('budget_used', 0)):.0%}"]
    commands = [item.get("command") for item in snapshot.get("commands", []) if item.get("state") == "active"][:5]
    if commands:
        lines += ["", "VERIFICATION", "  " + " · ".join(str(item) for item in commands)]
    lines += ["", _paint("Project facts are structural priors; verified outcomes remain separate evidence.", MUTED, enabled)]
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
