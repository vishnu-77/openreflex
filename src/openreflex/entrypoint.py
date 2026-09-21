"""Console entrypoint layering managed project memory + presentation over the stable CLI.

The existing CLI remains the source of truth for engine operations. This wrapper
adds non-blocking project-memory bootstrap, compact structural context on Claude
prompts, a Claude status line, and an optional TUI without changing normal agent
workflows. Every hook-side enhancement is fail-open: presentation/memory failures
must never block the coding agent.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

from . import __version__, cli
from .claude_ui import configure_statusline, remove_statusline
from .project import approval, log_error, project_root
from .project_map import enrich_snapshot
from .project_memory import ensure_background_refresh, load_snapshot, read_state, run_worker, update_state
from .privacy import categorize, file_paths
from .reflex_index import account_project_context, context_for_task, reinforce_latest_execution, sync_counts
from .tui import claude_project_from_stdin, dashboard, statusline

PROMPT_EVENTS = {"UserPromptSubmit"}
TOOL_START_EVENTS = {"PreToolUse"}
TOOL_END_EVENTS = {"PostToolUse", "PostToolUseFailure"}
STOP_EVENTS = {"Stop", "SessionEnd"}
SESSION_EVENTS = {"SessionStart"}
T = TypeVar("T")

ACTIVITY_LABELS = {
    "read": "READ",
    "search": "SEARCH",
    "edit": "EDIT",
    "test": "TEST",
    "lint": "LINT",
    "build": "BUILD",
    "vcs": "GIT",
    "web": "WEB",
    "delegate": "DELEGATE",
    "plan": "PLAN",
    "mcp": "MCP",
    "shell": "RUN",
    "other": "TOOL",
}


def _best_effort(label: str, call: Callable[[], T], default: T) -> T:
    try:
        return call()
    except Exception as error:  # noqa: BLE001 - optional vNext layers must not take the agent down
        log_error(f"vnext {label}: {type(error).__name__}: {error}")
        return default


def _project_arg(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item == "--project" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--project="):
            return item.partition("=")[2]
    return None


def _plugin_root_arg(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item == "--plugin-root" and index + 1 < len(argv):
            value = argv[index + 1]
            return None if "${" in value else value
        if item.startswith("--plugin-root="):
            value = item.partition("=")[2]
            return None if "${" in value else value
    return None


def _plugin_manifest_version(root: str | None) -> str | None:
    if not root:
        return None
    try:
        data = json.loads((Path(root) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        version = data.get("version") if isinstance(data, dict) else None
        return str(version).strip() if version else None
    except (OSError, ValueError):
        return None


def _record_hook_runtime(project: Path, argv: list[str]) -> None:
    """Record the versions Claude actually invoked, without persisting plugin cache paths."""
    state = read_state(project)
    plugin_version = _plugin_manifest_version(_plugin_root_arg(argv))
    fields: dict[str, object] = {}
    if state.get("hook_runtime_version") != __version__:
        fields["hook_runtime_version"] = __version__
        fields["hook_loaded_at"] = round(time.time(), 3)
    if plugin_version and state.get("plugin_version") != plugin_version:
        fields["plugin_version"] = plugin_version
        fields["plugin_loaded_at"] = round(time.time(), 3)
    if fields:
        update_state(project, **fields)


def _record_mcp_runtime(project: Path) -> None:
    """MCP startup is observable on session/plugin reload; record the executable version Claude started."""
    state = read_state(project)
    update_state(
        project,
        mcp_runtime_version=__version__,
        mcp_loaded_at=round(time.time(), 3),
        mcp_loads=int(state.get("mcp_loads", 0)) + 1,
    )


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
    reflex_name = None
    reflex_state = None
    previous_task = read_state(project).get("task") or {}
    mode = str(previous_task.get("mode") or "build")
    data = _output_dict(output)
    hook = data.get("hookSpecificOutput") if isinstance(data, dict) else {}
    text = hook.get("additionalContext", "") if isinstance(hook, dict) else ""
    match = re.search(r"(\d+) similar past task", text)
    if match:
        experiences = int(match.group(1))
    # 0.7+ Reflex context is "Reflex: <name> · learned/proven."; keep the old mode-bearing
    # parser as a compatibility fallback for sessions that have not yet restarted after an upgrade.
    match = re.search(
        r"\[OpenReflex\]\s+Reflex:\s*([^·\n]+)\s*·\s*(candidate|learned|proven|stale)\.?",
        text,
        re.I,
    )
    if match:
        reflex_name = match.group(1).strip()
        reflex_state = match.group(2).lower()
    else:
        match = re.search(r"\[OpenReflex\]\s+Reflex:\s*([^·|\n]+)\s*·\s*(BUILD|INVESTIGATE|THINK)", text, re.I)
        if match:
            reflex_name = match.group(1).strip()
            mode = match.group(2).lower()
    match = re.search(r"Suggested path:\s*([a-z0-9_-]+)", text, re.I)
    if match:
        route = match.group(1)
    alternatives = None
    match = re.search(r"Alternatives:\s*(.+)", text)
    if match:
        alternatives = match.group(1).strip()
    match = re.search(r"\[OpenReflex\]\s+(BUILD|INVESTIGATE|THINK)", text, re.I)
    if match:
        mode = match.group(1).lower()
    task = {"active": True, "mode": mode}
    if reflex_name:
        task["reflex"] = reflex_name
    if reflex_state:
        task["reflex_state"] = reflex_state
    if route:
        task["route"] = route
    if alternatives:
        task["alternatives"] = alternatives
    # A new prompt is a new task surface. Do not carry the previous task's call count/activity into it.
    phase = "recall" if experiences or reflex_name or project_context else ("investigate" if mode == "investigate" else
                                                              "think" if mode == "think" else "watch")
    update_state(project, phase, recall={"experiences": experiences}, task=task,
                 execution={"calls": 0}, activity={})


def _activity(project: Path, payload: dict, *, status: str) -> dict:
    tool = str(payload.get("tool_name") or "")
    arguments = payload.get("tool_input") or {}
    category = categorize(tool, arguments)
    paths = file_paths(arguments, project)
    activity = {
        "category": category,
        "label": ACTIVITY_LABELS.get(category, "TOOL"),
        "status": status,
    }
    if paths:
        activity["target"] = paths[0]
    return activity


def _tool_start_state(project: Path, payload: dict) -> None:
    activity = _activity(project, payload, status="running")
    state = read_state(project)
    execution = dict(state.get("execution") or {})
    execution.setdefault("calls", 0)
    mode = str((state.get("task") or {}).get("mode") or "build")
    phase = ("verify" if activity["category"] in {"test", "lint", "build"} else
             "investigate" if mode == "investigate" else "think" if mode == "think" else "watch")
    update_state(project, phase, execution=execution, activity=activity,
                 verification=activity["label"].lower() if phase == "verify" else None)


def _tool_end_state(project: Path, payload: dict, *, failed: bool = False) -> None:
    state = read_state(project)
    execution = dict(state.get("execution") or {})
    execution["calls"] = int(execution.get("calls", 0)) + 1
    activity = _activity(project, payload, status="failed" if failed else "complete")
    mode = str((state.get("task") or {}).get("mode") or "build")
    phase = ("verify" if activity["category"] in {"test", "lint", "build"} else
             "investigate" if mode == "investigate" else "think" if mode == "think" else "watch")
    update_state(project, phase, execution=execution, activity=activity,
                 verification=activity["label"].lower() if phase == "verify" else None)


def _needs_verification(output: str) -> bool:
    data = _output_dict(output)
    hook = data.get("hookSpecificOutput") if isinstance(data, dict) else {}
    context = hook.get("additionalContext", "") if isinstance(hook, dict) else ""
    return isinstance(context, str) and "OpenReflex cannot verify this changed task yet" in context


def _stop_state(project: Path, agent: str, session: str, output: str, payload: dict | None = None) -> None:
    payload = payload or {}
    state = read_state(project)
    task = dict(state.get("task") or {})
    background = payload.get("background_tasks")
    crons = payload.get("session_crons")
    pending_background = len(background) if isinstance(background, list) else 0
    pending_crons = len(crons) if isinstance(crons, list) else 0
    if pending_background or pending_crons:
        task["active"] = True
        update_state(project, "waiting", outcome="work still scheduled", task=task, activity={},
                     pending={"background": pending_background, "scheduled": pending_crons})
        return
    if _needs_verification(output):
        task["active"] = True
        update_state(project, "verify", outcome="verification required", verification="pending",
                     task=task, activity={})
        return

    outcome = "execution captured"
    data = _output_dict(output)
    notice = str(data.get("systemMessage") or "") if isinstance(data, dict) else ""
    match = re.search(r"(?:COMPLETE|FAILED|UNVERIFIED|FINISHED)\s*\n\s*([^\s·]+)", notice)
    if match:
        outcome = match.group(1)
    reinforce_latest_execution(project, agent, session)
    task["active"] = False
    update_state(project, "remember", outcome=outcome, execution={}, task=task, activity={})


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

    if enabled:
        _best_effort("record hook runtime", lambda: _record_hook_runtime(project, argv), None)

    if enabled and event in SESSION_EVENTS:
        if agent == "claude-code":
            _best_effort("configure statusline", lambda: configure_statusline(project), "unavailable")
            def _tokens_start():
                from .usage import configured, ensure_receiver, register_session
                register_session(project, session)
                active = ensure_receiver() if configured() else False
                update_state(project, token_tracking="active" if active else "off")
                return active
            _best_effort("token tracking", _tokens_start, False)
        phase = _best_effort("start primer", lambda: ensure_background_refresh(project), "cold")
        _best_effort("sync counts", lambda: sync_counts(project), {})

    # PreToolUse is the only moment the statusline can truthfully show what is running right now.
    if enabled and event in TOOL_START_EVENTS:
        _best_effort("update live tool state", lambda: _tool_start_state(project, payload), None)

    output = safe_handle(agent, event, raw)

    if enabled and event in SESSION_EVENTS and phase in {"reflexing", "refreshing"}:
        verb = "understanding this project" if phase == "reflexing" else "refreshing project memory"
        output = _merge_notice(output, f"↺ OpenReflex v{__version__} · {phase.upper()}\n{verb} · work normally")
    elif enabled and agent == "claude-code" and event in PROMPT_EVENTS:
        prompt = payload.get("prompt") if isinstance(payload.get("prompt"), str) else ""
        project_context = (_best_effort("retrieve project memory", lambda: context_for_task(project, prompt), None)
                           if is_substantial(prompt) else None)
        if project_context:
            output = _merge_project_context(output, project_context, event)
            _best_effort("account project context",
                         lambda: account_project_context(project, agent, session, project_context), None)
        _best_effort("update prompt state", lambda: _prompt_state(project, output, project_context), None)
    elif enabled and event in TOOL_END_EVENTS:
        _best_effort("update tool state",
                     lambda: _tool_end_state(project, payload, failed=event == "PostToolUseFailure"), None)
    elif enabled and event in STOP_EVENTS:
        _best_effort("reinforce outcome", lambda: _stop_state(project, agent, session, output, payload), None)

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
        _best_effort("TUI primer", lambda: ensure_background_refresh(project), "cold")
        _best_effort("TUI counts", lambda: sync_counts(project), {})
    print(dashboard(project))
    return 0


def _refresh_memory(project: Path, rebuild: bool = False) -> dict:
    if rebuild:
        from .project_memory import snapshot_path
        snapshot_path(project).unlink(missing_ok=True)
    result = run_worker(project)
    _best_effort("project map", lambda: enrich_snapshot(project), {})
    sync_counts(project)
    return result


def _memory(argv: list[str]) -> int:
    project = project_root(_project_arg(argv))
    action = argv[0] if argv and not argv[0].startswith("-") else "status"
    if action in {"refresh", "rebuild"}:
        result = _refresh_memory(project, rebuild=action == "rebuild")
        print(f"OPENREFLEX / MEMORY\n  action      {action}\n  state       ready\n  generation  {result.get('generation', 0)}")
        return 0
    sync_counts(project)
    snapshot, state = load_snapshot(project), read_state(project)
    project_map = snapshot.get("project_map") or {}
    print("OPENREFLEX / MEMORY")
    print(f"  project     {project}")
    print(f"  state       {state.get('memory', 'cold')}")
    print(f"  type        {snapshot.get('project_kind', '-')}")
    print(f"  generation  {snapshot.get('generation', 0)}")
    print(f"  facts       {sum(f.get('state') == 'active' for f in snapshot.get('facts', []))} active / "
          f"{sum(f.get('state') == 'stale' for f in snapshot.get('facts', []))} stale")
    print(f"  files       {len(snapshot.get('indexed_files', []))} indexed / {project_map.get('tracked_files', 0)} tracked")
    print(f"  deps        {len(project_map.get('dependencies', []))}")
    print(f"  relations   {len(project_map.get('relationships', []))}")
    print(f"  experiences {state.get('experiences', 0)}")
    print(f"  outcomes    {state.get('known_outcomes', 0)} known / {state.get('verified', 0)} verified")
    print(f"  lessons     {state.get('lessons', 0)}")
    return 0




def _reflexes(argv: list[str]) -> int:
    from .reflexes import visible_reflexes
    from .store import Store, database_path

    if argv and argv[0] in {"-h", "--help"}:
        print("usage: openreflex reflexes [--project PATH]\n")
        print("Show learned and proven project-specific Reflex procedures.")
        return 0
    project = project_root(_project_arg(argv))
    store = Store(database_path(project))
    try:
        reflexes = visible_reflexes(store)
    finally:
        store.close()
    print("OPENREFLEX / PROJECT REFLEXES")
    print(f"  project     {project}")
    if not reflexes:
        print("  state       learning")
        print("  reflexes    none learned yet")
        return 0
    for reflex in reflexes:
        print("")
        print(f"  {reflex.name}")
        print(f"    state     {reflex.state}")
        print(f"    evidence  {reflex.success_count} successful / {reflex.verified_count} verified")
        if reflex.family.startswith("area:"):
            print("    scope     cross-task project area")
        else:
            print(f"    steps     {' -> '.join(reflex.procedure)}")
    return 0


def _tokens(argv: list[str]) -> int:
    from .usage import configured, disable, enable, receiver_running, serve

    action = argv[0] if argv else "status"
    if action in {"-h", "--help"}:
        print("usage: openreflex tokens {enable,disable,status}\n")
        print("  enable   Turn on local Claude Code token accounting (loopback receiver)")
        print("  disable  Turn off token accounting and stop the receiver")
        print("  status   Show whether tracking is configured and whether the receiver is running")
        return 0
    if action == "serve":
        serve()
        return 0
    if action == "enable":
        result = enable()
        print("OPENREFLEX / TOKENS")
        if result["status"] == "conflict":
            print("  state       not changed")
            print("  reason      existing Claude telemetry settings are user-owned")
            print("  conflicts   " + ", ".join(result["keys"]))
            return 2
        print("  state       enabled")
        print("  source      Claude Code api_request telemetry")
        print("  privacy     counts only; prompt/response/tool content disabled")
        print("  receiver    " + ("running" if receiver_running() else "configured"))
        print("\nRestart or reload Claude Code so its telemetry environment is refreshed.")
        return 0
    if action == "disable":
        result = disable()
        print("OPENREFLEX / TOKENS")
        print(f"  state       {result['status']}")
        return 0
    if action == "status":
        print("OPENREFLEX / TOKENS")
        print(f"  configured  {configured()}")
        print(f"  receiver    {'running' if receiver_running() else 'stopped'}")
        print("  captures    input, output, cache read, cache creation, model, source, estimated cost")
        print("  content     prompts/responses/thinking/tool arguments are not collected")
        return 0
    print(f"Unknown tokens action: {action}")
    print("usage: openreflex tokens {enable,disable,status}")
    return 2


def _augment_install(argv: list[str], result: int) -> None:
    if result != 0 or len(argv) < 2 or argv[1] != "claude-code" or "--dry-run" in argv:
        return
    project = project_root(_project_arg(argv))
    status = configure_statusline(project)
    if status == "configured":
        print(f"  statusline  OpenReflex v{__version__} enabled")
    elif status == "preserved-existing":
        print("  statusline  existing user status line preserved")


def _augment_uninstall(argv: list[str], result: int) -> None:
    if result != 0 or len(argv) < 2 or argv[1] != "claude-code" or "--dry-run" in argv:
        return
    project = project_root(_project_arg(argv))
    if remove_statusline(project):
        print("  statusline  OpenReflex status line removed")


def main(argv: list[str] | None = None) -> int:
    cli._utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return _tui([])
    if argv[0] == "hook":
        return _hook(argv)
    if argv[0] == "primer-worker":
        project = project_root(_project_arg(argv))
        run_worker(project)
        _best_effort("project map", lambda: enrich_snapshot(project), {})
        return 0
    if argv[0] == "statusline":
        return _statusline()
    if argv[0] == "tui":
        return _tui(argv[1:])
    if argv[0] == "memory":
        return _memory(argv[1:])
    if argv[0] == "reflexes":
        return _reflexes(argv[1:])
    if argv[0] == "tokens":
        return _tokens(argv[1:])
    if argv[0] == "mcp":
        project = project_root(_project_arg(argv))
        if approval(project):
            _best_effort("record MCP runtime", lambda: _record_mcp_runtime(project), None)
        return cli.main(argv)

    result = cli.main(argv)
    if argv[0] == "install":
        _augment_install(argv, result)
    elif argv[0] == "uninstall":
        _augment_uninstall(argv, result)
    return result
