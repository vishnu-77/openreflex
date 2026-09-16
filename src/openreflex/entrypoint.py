"""Console entrypoint layering managed project memory + presentation over the stable CLI.

The existing CLI remains the source of truth for engine operations. This wrapper
adds non-blocking project-memory bootstrap, compact structural context on Claude
prompts, a Claude status line, and an optional TUI without changing normal agent
workflows.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import cli
from .claude_ui import configure_statusline, remove_statusline
from .project import approval, project_root
from .project_memory import ensure_background_refresh, load_snapshot, read_state, run_worker, update_state
from .privacy import categorize
from .reflex_index import account_project_context, context_for_task, reinforce_latest_execution, sync_counts
from .tui import claude_project_from_stdin, dashboard, statusline

PROMPT_EVENTS = {"UserPromptSubmit"}
TOOL_END_EVENTS = {"PostToolUse", "PostToolUseFailure"}
STOP_EVENTS = {"Stop", "SessionEnd"}
SESSION_EVENTS = {"SessionStart"}


def _project_arg(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item == "--project" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--project="):
            return item.partition("=")[2]
    return None


def _payload(raw: str) -> dict:
    try:
        value = json.loads(raw) if raw.strip() else {}
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _output_dict(output: str) -> dict:
    try:
        value = json.loads(output) if output else {}
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _merge_project_context(output: str, project_context: str, event: str) -> str:
    data = _output_dict(output)
    hook = data.setdefault("hookSpecificOutput", {"hookEventName": event})
    if not isinstance(hook, dict):
        hook = {"hookEventName": event}
        data["hookSpecificOutput"] = hook
    existing = hook.get("additionalContext")
    hook["hookEventName"] = event
    hook["additionalContext"] = "\n\n".join(part for part in (existing, project_context)
                                               if isinstance(part, str) and part)
    return json.dumps(data)


def _merge_notice(output: str, notice: str) -> str:
    data = _output_dict(output)
    existing = data.get("systemMessage")
    data["systemMessage"] = "\n\n".join(part for part in (existing, notice) if isinstance(part, str) and part)
    return json.dumps(data)


def _prompt_state(project: Path, output: str, project_context: str | None) -> None:
    experiences = 0
    route = None
    data = _output_dict(output)
    hook = data.get("hookSpecificOutput") if isinstance(data, dict) else {}
    text = hook.get("additionalContext", "") if isinstance(hook, dict) else ""
    match = re.search(r"(\d+) similar past task", text)
    if match:
        experiences = int(match.group(1))
    match = re.search(r"Suggested path:\s*([a-z0-9_-]+)", text, re.I)
    if match:
        route = match.group(1)
    update_state(project, "recall" if experiences or project_context else "watch",
                 recall={"experiences": experiences}, task={"route": route} if route else {})


def _tool_state(project: Path, payload: dict) -> None:
    state = read_state(project)
    execution = dict(state.get("execution") or {})
    execution["calls"] = int(execution.get("calls", 0)) + 1
    category = categorize(str(payload.get("tool_name") or ""), payload.get("tool_input") or {})
    if category in {"test", "lint", "build"}:
        update_state(project, "verify", execution=execution, verification=category)
    else:
        update_state(project, "watch", execution=execution)


def _stop_state(project: Path, agent: str, session: str, output: str) -> None:
    outcome = "execution captured"
    data = _output_dict(output)
    notice = str(data.get("systemMessage") or "") if isinstance(data, dict) else ""
    match = re.search(r"COMPLETE\s*\n\s*([^\s·]+)", notice)
    if match:
        outcome = match.group(1)
    reinforce_latest_execution(project, agent, session)
    update_state(project, "remember", outcome=outcome, execution={})


def _hook(argv: list[str]) -> int:
    from .engine import is_substantial
    from .hooks import safe_handle

    agent = argv[1] if len(argv) > 1 else ""
    event = argv[2] if len(argv) > 2 else ""
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    payload = _payload(raw)
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    session = str(payload.get("session_id") or payload.get("conversation_id") or "")
    project = project_root(cwd, hook_session=session)
    enabled = approval(project) is not None
    phase = None

    if enabled and event in SESSION_EVENTS:
        if agent == "claude-code":
            configure_statusline(project)  # no-op when the user already owns a custom status line
        phase = ensure_background_refresh(project)
        sync_counts(project)

    output = safe_handle(agent, event, raw)

    if enabled and event in SESSION_EVENTS and phase in {"reflexing", "refreshing"}:
        verb = "understanding this project" if phase == "reflexing" else "refreshing project memory"
        output = _merge_notice(output, f"↺ OpenReflex · {phase.upper()}\n{verb} · work normally")
    elif enabled and agent == "claude-code" and event in PROMPT_EVENTS:
        prompt = payload.get("prompt") if isinstance(payload.get("prompt"), str) else ""
        project_context = context_for_task(project, prompt) if is_substantial(prompt) else None
        if project_context:
            output = _merge_project_context(output, project_context, event)
            account_project_context(project, agent, session, project_context)
        _prompt_state(project, output, project_context)
    elif enabled and event in TOOL_END_EVENTS:
        _tool_state(project, payload)
    elif enabled and event in STOP_EVENTS:
        _stop_state(project, agent, session, output)

    if output:
        sys.stdout.write(output)
        sys.stdout.flush()
    return 0


def _statusline() -> int:
    """Render from cached state only; never scan, query git, or open the Experience Graph on the refresh path."""
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    hinted = claude_project_from_stdin(raw)
    project = project_root(hinted)
    print(statusline(project, force_colour=True))
    return 0


def _tui(argv: list[str]) -> int:
    project = project_root(_project_arg(argv))
    if approval(project):
        ensure_background_refresh(project)
        sync_counts(project)
    print(dashboard(project))
    return 0


def _memory(argv: list[str]) -> int:
    project = project_root(_project_arg(argv))
    action = argv[0] if argv and not argv[0].startswith("-") else "status"
    if action in {"refresh", "rebuild"}:
        if action == "rebuild":
            from .project_memory import snapshot_path
            snapshot_path(project).unlink(missing_ok=True)
        result = run_worker(project)
        sync_counts(project)
        print(f"OPENREFLEX / MEMORY\n  action      {action}\n  state       ready\n  generation  {result.get('generation', 0)}")
        return 0
    sync_counts(project)
    snapshot, state = load_snapshot(project), read_state(project)
    print("OPENREFLEX / MEMORY")
    print(f"  project     {project}")
    print(f"  state       {state.get('memory', 'cold')}")
    print(f"  type        {snapshot.get('project_kind', '-')}")
    print(f"  generation  {snapshot.get('generation', 0)}")
    print(f"  facts       {sum(f.get('state') == 'active' for f in snapshot.get('facts', []))} active / "
          f"{sum(f.get('state') == 'stale' for f in snapshot.get('facts', []))} stale")
    print(f"  files       {len(snapshot.get('indexed_files', []))} indexed")
    print(f"  experiences {state.get('experiences', 0)}")
    print(f"  outcomes    {state.get('known_outcomes', 0)} known / {state.get('verified', 0)} verified")
    print(f"  lessons     {state.get('lessons', 0)}")
    return 0


def _augment_install(argv: list[str], result: int) -> None:
    if result != 0 or len(argv) < 2 or argv[1] != "claude-code" or "--dry-run" in argv:
        return
    project = project_root(_project_arg(argv))
    status = configure_statusline(project)
    if status == "configured":
        print("  statusline  OpenReflex enabled")
    elif status == "preserved-existing":
        print("  statusline  existing user status line preserved")


def _augment_uninstall(argv: list[str], result: int) -> None:
    if result != 0 or len(argv) < 2 or argv[1] != "claude-code" or "--dry-run" in argv:
        return
    project = project_root(_project_arg(argv))
    if remove_statusline(project):
        print("  statusline  OpenReflex status line removed")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return _tui([])
    if argv[0] == "hook":
        return _hook(argv)
    if argv[0] == "primer-worker":
        project = project_root(_project_arg(argv))
        run_worker(project)
        return 0
    if argv[0] == "statusline":
        return _statusline()
    if argv[0] == "tui":
        return _tui(argv[1:])
    if argv[0] == "memory":
        return _memory(argv[1:])

    result = cli.main(argv)
    if argv[0] == "install":
        _augment_install(argv, result)
    elif argv[0] == "uninstall":
        _augment_uninstall(argv, result)
    return result
