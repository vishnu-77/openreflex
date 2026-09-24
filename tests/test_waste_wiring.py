"""Wasted-effort signals reach the agent and the status line, and novel tasks are recognised."""

import dataclasses
import json

from openreflex import entrypoint
from openreflex.engine import Engine
from openreflex.project import approve
from openreflex.tui import statusline

from .test_hooks import call, factory  # noqa: F401 - shared fixture


def work(engine, clock, n, tool="Edit", success=True, error=None, chars=800, same=False):
    messages = []
    for i in range(n):
        clock.advance(200)  # past the alert cooldown each time
        arguments = {"file_path": "src/app.py" if same else f"src/m{i}.py"}
        engine.tool_start("claude-code", "s1", f"t{clock()}", tool, arguments)
        messages.append(engine.tool_end("claude-code", "s1", f"t{clock()}", tool, arguments, success, error, chars))
    return [m for m in messages if m]


def test_repeated_identical_call_is_flagged(engine, clock):
    engine.prompt("claude-code", "s1", "Explain how the payment webhook verification works end to end")
    said = work(engine, clock, 3, tool="Read", same=True)
    assert any("same Read call ran 3x" in m and "Reuse the earlier result" in m for m in said), said


def test_tool_output_over_the_token_budget_advises_targeted_reads(engine, clock):
    engine.prompt("claude-code", "s1", "Explain how the payment webhook verification works end to end")
    said = work(engine, clock, 1, tool="Read", chars=140_000)  # ~35k tokens against a ~30k budget
    assert said and "tokens of tool output" in said[0] and "targeted reads" in said[0], said


def test_over_budget_fires_while_still_editing_and_escalates(engine, clock, monkeypatch):
    monkeypatch.setenv("OPENREFLEX_BUDGET", "calls=10")
    engine.prompt("claude-code", "s1", "Add rate limiting to the public search endpoint with tests")
    said = " | ".join(work(engine, clock, 25))  # every call is a successful edit: busy, but far past budget
    tiers = [said.find(text) for text in ("re-plan before continuing", "re-scope with the user", "double the budget")]
    assert -1 not in tiers and tiers == sorted(tiers), said


def test_cursor_failure_alert_waits_for_the_next_visible_event(project, factory, clock):  # noqa: F811
    approve(project)
    base = {"conversation_id": "c", "generation_id": "g", "workspace_roots": [str(project)], "cursor_version": "2.0"}
    call("cursor", "beforeSubmitPrompt", {**base, "prompt": "Fix the flaky payment webhook signature check"}, factory)
    for i in range(3):
        clock.advance(200)
        payload = {**base, "tool_name": "Shell", "tool_input": {"command": f"pytest -k case{i}"}, "tool_use_id": f"f{i}"}
        call("cursor", "preToolUse", payload, factory)
        failed = call("cursor", "postToolUseFailure", {**payload, "error_message": f"E  ValueError: case {i}"}, factory)
        assert json.loads(failed) == {}, "cursor cannot show context on postToolUseFailure"
    payload = {**base, "tool_name": "Read", "tool_input": {"file_path": "src/webhook.py"}, "tool_use_id": "r"}
    call("cursor", "preToolUse", payload, factory)
    shown = json.loads(call("cursor", "postToolUse", {**payload, "tool_output": "{}"}, factory))
    assert "consecutive tool failures" in shown["additional_context"]
    payload["tool_use_id"] = "r2"
    call("cursor", "preToolUse", payload, factory)
    assert json.loads(call("cursor", "postToolUse", {**payload, "tool_output": "{}"}, factory)) == {}, "delivered once"


def test_opencode_error_alert_is_delivered_on_the_next_tool_after(project, factory, clock):  # noqa: F811
    approve(project)
    base = {"session_id": "o", "cwd": str(project)}
    call("opencode", "chat.message", {**base, "prompt": "Implement dark mode toggle in the settings page"}, factory)
    for i in range(3):
        clock.advance(200)
        tool = {**base, "tool": "bash", "call_id": f"k{i}", "args": {"command": f"npm test -- case{i}"}}
        call("opencode", "tool.before", tool, factory)
        assert json.loads(call("opencode", "tool.error", {**tool, "error": f"Error: case {i}"}, factory))["context"] is None
    tool = {**base, "tool": "read", "call_id": "r", "args": {"filePath": str(project / "src" / "theme.ts")}}
    call("opencode", "tool.before", tool, factory)
    after = json.loads(call("opencode", "tool.after", {**tool, "output": "..."}, factory))
    assert "consecutive tool failures" in (after["context"] or "")


def test_statusline_shows_budget_use_and_pivot_advice(project, monkeypatch):
    monkeypatch.setenv("OPENREFLEX_BUDGET", "calls=4")
    engine = Engine(project)
    try:
        engine.prompt("claude-code", "s1", "Add rate limiting to the public search endpoint with tests")
        for i in range(6):
            arguments = {"file_path": f"src/m{i}.py"}
            engine.tool_start("claude-code", "s1", f"t{i}", "Edit", arguments)
            engine.tool_end("claude-code", "s1", f"t{i}", "Edit", arguments, True, None, 100)
    finally:
        engine.close()
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/m5.py"}}
    entrypoint._tool_end_state(project, payload, agent="claude-code", session="s1")
    assert "budget 150%" in statusline(project, force_colour=False)

    monkeypatch.setattr(entrypoint, "_runtime_status", lambda *_: {"budget_used": 2.1, "advice": "stop"})
    entrypoint._tool_end_state(project, payload, agent="claude-code", session="s1")
    shown = statusline(project, force_colour=False)
    assert "PIVOT" in shown and "budget 210%" in shown


def seed(engine, clock, prompts):
    for i, prompt in enumerate(prompts):
        engine.prompt("claude-code", f"seed{i}", prompt)
        clock.advance(5)
        arguments = {"command": "pytest -q"}
        engine.tool_start("claude-code", f"seed{i}", f"x{i}", "Bash", arguments)
        engine.tool_end("claude-code", f"seed{i}", f"x{i}", "Bash", arguments, True, None, 100)
        engine.stop("claude-code", f"seed{i}")
        clock.advance(600)


HISTORY = ["Fix the login redirect loop after logout", "Fix the login token refresh race",
           "Fix the login page error message on bad password", "Add pagination to the orders list API",
           "Add CSV export to the orders report"]


def test_novelty_is_unknown_until_the_project_has_history(engine, clock):
    seed(engine, clock, HISTORY[:2])
    context = engine.prompt("claude-code", "s1", "Migrate the build pipeline from setuptools to hatch")
    task = engine.store.list("Task", "session_id", "s1")[0]
    assert task.novelty == "unknown" and context is None


def test_novel_task_is_flagged_with_a_wider_budget(engine, clock):
    seed(engine, clock, HISTORY)
    routine_budget = engine.store.latest("claude-code", "seed4").budget_tool_calls
    context = engine.prompt("claude-code", "s1", "Migrate the build pipeline from setuptools to hatch")
    execution = engine.store.latest("claude-code", "s1")
    assert engine._task(execution).novelty == "novel"
    assert context and "Novel task for this project" in context
    assert execution.budget_tool_calls > routine_budget

    engine.prompt("claude-code", "s2", "Fix the login redirect loop when the session cookie expires")
    assert engine._task(engine.store.latest("claude-code", "s2")).novelty == "routine"


def test_novel_budget_never_exceeds_a_user_limit(engine, clock, monkeypatch):
    seed(engine, clock, HISTORY)
    monkeypatch.setenv("OPENREFLEX_BUDGET", "calls=12")
    engine.prompt("claude-code", "s1", "Migrate the build pipeline from setuptools to hatch")
    assert engine.store.latest("claude-code", "s1").budget_tool_calls == 12


def test_check_progress_reports_a_stop_even_without_fresh_problems(project, monkeypatch):
    from openreflex import detect
    from openreflex.mcp_server import build_server

    from .test_mcp_metrics_benchmark import tool_text

    approve(project)
    server = build_server(project)
    tool_text(server, "get_execution_context", {"task": "Fix the flaky payment webhook signature check"})
    verdict = Engine._verdict
    monkeypatch.setattr(Engine, "_verdict", lambda *a: dataclasses.replace(verdict(*a), action="stop"))
    monkeypatch.setattr(detect, "detect", lambda *a, **k: [])
    assert tool_text(server, "check_progress", {}).startswith("Recommendation: stop")
