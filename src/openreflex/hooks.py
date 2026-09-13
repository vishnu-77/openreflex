"""Lifecycle-hook adapters: translate each agent's hook payloads to engine calls and render its output format.

Supported agents and their native hook protocols:
  claude-code  SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure, PreCompact, Stop, SessionEnd
  codex        same names as Claude Code; there is no failure event, so failures are read from tool_response
  cursor       sessionStart, beforeSubmitPrompt, preToolUse, postToolUse, postToolUseFailure, preCompact, stop,
               sessionEnd; context can only be injected on sessionStart/postToolUse, so prompt-time context is
               delivered with the first tool result
  opencode     events forwarded by plugins/opencode/openreflex.ts (see that file)

A hook must never break the agent: every failure path degrades to an empty, non-blocking response.
"""

import json
import os
import random
import re
import sqlite3
import time
import traceback
from dataclasses import dataclass, field

from .engine import Engine
from .project import approval, log_error, project_root, should_notify_unapproved

AGENTS = ("claude-code", "codex", "cursor", "opencode")


@dataclass
class Event:
    kind: str  # session_start | prompt | tool_start | tool_end | compaction | stop | ignored
    session: str
    cwd: str | None
    prompt: str = ""
    tool: str = ""
    tool_id: str | None = None
    arguments: object = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    output_chars: int = 0


CLAUDE_KINDS = {"SessionStart": "session_start", "UserPromptSubmit": "prompt", "PreToolUse": "tool_start",
                "PostToolUse": "tool_end", "PostToolUseFailure": "tool_end", "PreCompact": "compaction",
                "PostCompact": "ignored", "Stop": "stop", "SessionEnd": "stop"}
CURSOR_KINDS = {"sessionStart": "session_start", "beforeSubmitPrompt": "prompt", "preToolUse": "tool_start",
                "postToolUse": "tool_end", "postToolUseFailure": "tool_end", "preCompact": "compaction",
                "stop": "stop", "sessionEnd": "stop"}
OPENCODE_KINDS = {"session.created": "session_start", "chat.message": "prompt", "tool.before": "tool_start",
                  "tool.after": "tool_end", "tool.error": "tool_end", "session.compacted": "compaction",
                  "session.idle": "stop", "session.deleted": "stop"}
EXIT_CODE = re.compile(r"(?im)(?:^exit code|exit(?:ed)? with (?:code|status)|exit status|exit_code[\"']?)\s*[:=]?\s*(-?\d+)")


def _size(value: object) -> int:
    if value is None:
        return 0
    return len(value) if isinstance(value, str) else len(json.dumps(value, default=str))


def response_failure(response: object) -> tuple[bool, str | None]:
    """Best-effort failure detection for agents that report failures inside a normal tool result."""
    if isinstance(response, dict):
        if response.get("is_error") or response.get("isError") or response.get("success") is False \
                or response.get("interrupted") is True:
            return True, str(response.get("error") or response.get("stderr") or response.get("output") or "tool error")
        for key in ("exit_code", "exitCode", "returncode", "status_code"):
            code = response.get(key)
            if isinstance(code, int) and code != 0:
                return True, str(response.get("stderr") or response.get("output") or response.get("stdout")
                                 or f"Exit code {code}")
        return False, None
    if isinstance(response, str):
        match = EXIT_CODE.search(response[:400])
        if match and int(match.group(1)) != 0:
            return True, response[:4000]
    return False, None


def detect_agent(agent: str, payload: dict) -> str:
    # Cursor can execute Claude Code hook configs; attribute those calls to Cursor so events deduplicate.
    if "cursor_version" in payload or ("conversation_id" in payload and "session_id" not in payload):
        return "cursor"
    return agent


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _ident(value: object) -> str:
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


def _message(value: object, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return json.dumps(value, default=str)[:4000] if value not in (None, "", {}, []) else default


def _arguments(value: object) -> object:
    return value if isinstance(value, (dict, list, str)) else {}


def normalize(agent: str, name: str, payload: dict) -> Event:
    """Map a native payload to an Event. Wrong-typed fields are coerced, so one odd field never drops an event."""
    if agent in ("claude-code", "codex"):
        name = name or _text(payload, "hook_event_name")
        event = Event(CLAUDE_KINDS.get(name, "ignored"), _ident(payload.get("session_id")), _text(payload, "cwd") or None,
                      prompt=_text(payload, "prompt"), tool=_text(payload, "tool_name"),
                      tool_id=_ident(payload.get("tool_use_id")) or None, arguments=_arguments(payload.get("tool_input")))
        if name == "PostToolUseFailure":
            event.success = False
            interrupted = payload.get("is_interrupt") is True
            event.error = "interrupted by user" if interrupted else _message(payload.get("error"), "tool failed")
            event.output_chars = _size(payload.get("error"))
        elif name == "PostToolUse":
            response = payload.get("tool_response")
            event.output_chars = _size(response)
            failed, error = response_failure(response)
            event.success, event.error = not failed, error
        return event

    if agent == "cursor":
        name = name or _text(payload, "hook_event_name")
        raw_roots = payload.get("workspace_roots")
        roots = [root for root in raw_roots if isinstance(root, str)] if isinstance(raw_roots, list) else []
        cwd = _text(payload, "cwd") or (roots[0] if roots else None) or os.environ.get("CURSOR_PROJECT_DIR")
        event = Event(CURSOR_KINDS.get(name, "ignored"),
                      _ident(payload.get("conversation_id")) or _ident(payload.get("session_id")), cwd,
                      prompt=_text(payload, "prompt"), tool=_text(payload, "tool_name"),
                      tool_id=_ident(payload.get("tool_use_id")) or None, arguments=_arguments(payload.get("tool_input")))
        if name == "postToolUseFailure":
            event.success = False
            event.error = _message(payload.get("error_message"), _text(payload, "failure_type") or "tool failed")
            event.output_chars = _size(payload.get("error_message"))
        elif name == "postToolUse":
            output = payload.get("tool_output")
            event.output_chars = _size(output)
            try:
                parsed = json.loads(output) if isinstance(output, str) else output
            except ValueError:
                parsed = output
            failed, error = response_failure(parsed)
            event.success, event.error = not failed, error
        return event

    if agent == "opencode":
        name = name or _text(payload, "event")
        chars = payload.get("output_chars")
        event = Event(OPENCODE_KINDS.get(name, "ignored"), _ident(payload.get("session_id")), _text(payload, "cwd") or None,
                      prompt=_text(payload, "prompt"), tool=_text(payload, "tool"),
                      tool_id=_ident(payload.get("call_id")) or None, arguments=_arguments(payload.get("args")),
                      output_chars=int(chars) if isinstance(chars, (int, float)) and chars >= 0 else 0)
        if name == "tool.error":
            event.success, event.error = False, _message(payload.get("error"), "tool failed")
        return event
    raise ValueError(f"Unsupported agent: {agent}")


def render(agent: str, name: str, context: str | None, notice: str | None = None) -> str:
    """Produce stdout in the agent's native hook output format. Empty output means 'no opinion'."""
    if agent in ("claude-code", "codex"):
        output: dict = {}
        if context and name in {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"}:
            output["hookSpecificOutput"] = {"hookEventName": name, "additionalContext": context}
        if notice:
            output["systemMessage"] = notice
        return json.dumps(output) if output else ""
    if agent == "cursor":
        if name == "beforeSubmitPrompt":
            return json.dumps({"continue": True})
        if context and name in {"sessionStart", "postToolUse"}:
            return json.dumps({"additional_context": context})
        return json.dumps({})
    if agent == "opencode":
        return json.dumps({"context": context, "notice": notice})
    return ""


def handle(agent: str, name: str, payload: dict, engine_factory=Engine) -> str:
    agent = detect_agent(agent, payload)
    name = name or payload.get("hook_event_name") or payload.get("event") or ""
    event = normalize(agent, name, payload)
    if event.kind == "ignored" or not event.session:
        return render(agent, name, None)
    project = project_root(event.cwd)
    if not approval(project):
        notice = None
        if event.kind in ("session_start", "prompt") and should_notify_unapproved(project):
            notice = (f"OpenReflex is installed but not enabled for {project.name}. "
                      "Run `openreflex approve` in this project to enable local execution memory.")
        return render(agent, name, None, notice)

    engine = engine_factory(project)
    try:
        context = None
        if event.kind == "prompt":
            context = engine.prompt(agent, event.session, event.prompt, can_inject=agent != "cursor")
        elif event.kind == "tool_start":
            context = engine.tool_start(agent, event.session, event.tool_id, event.tool, event.arguments)
        elif event.kind == "tool_end":
            alert = engine.tool_end(agent, event.session, event.tool_id, event.tool, event.arguments,
                                    event.success, event.error, event.output_chars)
            pending = engine.take_pending_context(agent, event.session) if agent == "cursor" else None
            context = "\n\n".join(part for part in (pending, alert) if part) or None
        elif event.kind == "compaction":
            engine.compaction(agent, event.session)
        elif event.kind == "stop":
            engine.stop(agent, event.session)
        return render(agent, name, context)
    finally:
        engine.close()


def safe_handle(agent: str, name: str, raw: str) -> str:
    started = time.monotonic()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be a JSON object")
        while True:
            try:
                return handle(agent, name, payload)
            except sqlite3.OperationalError as error:
                # SQLite can report "locked" immediately (without waiting) under heavy parallel hooks. Engine
                # operations are idempotent, so a brief retry is safe; slow lock waits are not retried.
                if "locked" not in str(error) or time.monotonic() - started > 3:
                    raise
                time.sleep(random.uniform(0.05, 0.3))
    except Exception as error:  # noqa: BLE001 - a hook must never take the agent down
        frames = [frame for frame in traceback.extract_tb(error.__traceback__) if "openreflex" in frame.filename]
        site = f" at {os.path.basename(frames[-1].filename)}:{frames[-1].lineno}" if frames else ""
        log_error(f"hook {agent} {name}: {type(error).__name__}: {error}{site}")
        try:
            return render(agent if agent in AGENTS else "claude-code", name, None)
        except Exception:  # noqa: BLE001
            return ""
