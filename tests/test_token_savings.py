"""Token-saving mechanisms: measured usage, the holdout, refused repeats, known fixes, and context resets."""

import json

from openreflex.metrics import project_metrics
from openreflex.policy import load_policy
from openreflex.project import approve

from .conftest import run_task
from .test_engine import FIX_SCRIPT, TEST
from .test_hooks import call, factory, seed_experience  # noqa: F401 - shared fixture

PROMPT = "Fix the login bug where expired tokens are accepted"


def _assistant(message_id, stamp, output, cache_read=100):
    usage = {"input_tokens": 10, "output_tokens": output, "cache_read_input_tokens": cache_read,
             "cache_creation_input_tokens": 5}
    return json.dumps({"type": "assistant", "timestamp": stamp, "message": {"id": message_id, "model": "m",
                                                                           "usage": usage}}) + "\n"


def test_transcript_usage_is_counted_once_per_call_including_subagents(engine, tmp_path):
    transcript = tmp_path / "proj" / "sess.jsonl"
    (transcript.parent / "sess" / "subagents").mkdir(parents=True)
    transcript.write_text(
        _assistant("old", "2023-11-14T20:00:00Z", 50)            # before this task started: not its cost
        + json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
        + _assistant("a", "2023-11-14T22:20:00Z", 1)
        + _assistant("a", "2023-11-14T22:20:01Z", 7)               # same response, final output count
        + _assistant("b", "2023-11-14T22:21:00Z", 3, cache_read=900), encoding="utf-8")
    (transcript.parent / "sess" / "subagents" / "agent-1.jsonl").write_text(
        _assistant("c", "2023-11-14T22:20:30Z", 2), encoding="utf-8")

    engine.prompt("claude-code", "sess", PROMPT)
    outcome = engine.stop("claude-code", "sess", transcript=str(transcript))
    assert (outcome.input_tokens, outcome.output_tokens) == (30, 12)
    assert outcome.cache_read_tokens == 1100 and outcome.cache_creation_tokens == 15
    assert engine.store.get_meta("session_context_tokens:sess") == "915", "last main call's context size"

    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(_assistant("d", "2023-11-14T22:30:00Z", 4))
    engine.prompt("claude-code", "sess", "Now add a regression test for the token expiry check")
    second = engine.stop("claude-code", "sess", transcript=str(transcript))
    assert second.output_tokens == 4, "only calls appended since the last read"


def test_holdout_records_the_task_but_shows_nothing(engine, clock, project):
    run_task(engine, clock, "s1", PROMPT, FIX_SCRIPT)  # leaves a resolution lesson worth injecting
    (project / ".openreflex.toml").write_text("[evaluation]\nholdout_percent = 100\n", encoding="utf-8")
    engine.policy = load_policy(project)
    outcome, messages = run_task(engine, clock, "s2", PROMPT, FIX_SCRIPT)
    assert messages == [None] * len(messages)
    assert engine.store.get(outcome.execution_id).holdout
    assert engine.store.list("Context", "task_id", engine.store.get(outcome.execution_id).task_id)[0].held_out
    assert project_metrics(engine)["holdout"]["held_out"]["n"] == 1


def test_identical_failing_call_is_refused_until_something_changes(engine, clock):
    engine.prompt("claude-code", "s1", PROMPT)
    for i in range(2):
        clock.advance(10)
        engine.tool_start("claude-code", "s1", f"t{i}", *TEST)
        engine.tool_end("claude-code", "s1", f"t{i}", *TEST, False, "E   AssertionError: expired token accepted")
    reason = engine.blocked_retry("claude-code", "s1", *TEST)
    assert reason and "already failed 2x" in reason and "nothing has changed" in reason

    clock.advance(10)
    edit = ("Edit", {"file_path": "src/auth.py", "old_string": "a", "new_string": "b"})
    engine.tool_start("claude-code", "s1", "e1", *edit)
    engine.tool_end("claude-code", "s1", "e1", *edit, True)
    assert engine.blocked_retry("claude-code", "s1", *TEST) is None, "an edit since the failure makes a retry fair"


def test_claude_code_pretooluse_denies_the_repeat(project, factory, clock):  # noqa: F811
    approve(project)
    base = {"session_id": "s", "cwd": str(project)}
    call("claude-code", "UserPromptSubmit", {**base, "prompt": PROMPT}, factory)
    payload = {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
    for i in range(2):
        clock.advance(10)
        call("claude-code", "PreToolUse", {**payload, "tool_use_id": f"t{i}"}, factory)
        call("claude-code", "PostToolUseFailure", {**payload, "tool_use_id": f"t{i}", "error": "E   KeyError: 'x'"}, factory)
    denied = json.loads(call("claude-code", "PreToolUse", {**payload, "tool_use_id": "t2"}, factory))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert len(factory(project).store.list("ToolCall")) == 2, "a refused call never ran"


def test_known_fix_is_shown_on_the_first_failure(engine, clock):
    run_task(engine, clock, "s1", PROMPT, FIX_SCRIPT)
    engine.prompt("claude-code", "s2", "Expired tokens are accepted again after the refactor")
    clock.advance(10)
    engine.tool_start("claude-code", "s2", "x1", *TEST)
    said = engine.tool_end("claude-code", "s2", "x1", *TEST, False, "E   AssertionError: expired token accepted")
    assert said and "resolved before in this project" in said and "src/auth.py" in said
    clock.advance(10)
    engine.tool_start("claude-code", "s2", "x2", *TEST)
    again = engine.tool_end("claude-code", "s2", "x2", *TEST, False, "E   AssertionError: expired token accepted")
    assert not again or "resolved before" not in again, "shown once per error"


def test_context_reset_hint_only_for_large_unrelated_history(engine):
    engine.prompt("claude-code", "s1", PROMPT)
    unrelated = "Write the quarterly billing export to CSV for the finance team"
    assert engine.context_reset_hint("claude-code", "s1", unrelated) is None, "small history"
    engine.store.set_meta("session_context_tokens:s1", "400000")
    assert engine.context_reset_hint("claude-code", "s1", PROMPT + " in the API too") is None, "related work"
    assert engine.context_reset_hint("claude-code", "s1", "Now extend the change above to the admin login") is None
    hint = engine.context_reset_hint("claude-code", "s1", unrelated)
    assert hint and "~400k tokens" in hint and "/clear" in hint
    assert engine.context_reset_hint("claude-code", "s1", unrelated) is None, "not repeated until history doubles"


def test_clear_hands_the_new_session_a_short_summary(project, factory, clock):  # noqa: F811
    approve(project)
    seed_experience(project, factory, clock)
    output = json.loads(call("claude-code", "SessionStart",
                             {"session_id": "fresh", "cwd": str(project), "source": "clear"}, factory))
    handoff = output["hookSpecificOutput"]["additionalContext"]
    assert "Context was cleared" in handoff and "expired tokens" in handoff and "src/auth.py" in handoff
    assert len(handoff) < 500
    startup = call("claude-code", "SessionStart", {"session_id": "other", "cwd": str(project), "source": "startup"},
                   factory)
    assert startup == "", "only /clear gets a handoff"
