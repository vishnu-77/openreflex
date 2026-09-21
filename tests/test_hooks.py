import json
from pathlib import Path

import pytest

from openreflex import hooks
from openreflex.engine import Engine
from openreflex.project import approve
from openreflex.store import Store


@pytest.fixture
def factory(tmp_path, clock):
    """Engine factory sharing one database and clock across hook invocations, like separate hook processes."""
    database = tmp_path / "hooks.sqlite3"

    def make(project: Path) -> Engine:
        return Engine(project, Store(database), clock=clock)
    return make


def call(agent, event, payload, factory):
    return hooks.handle(agent, event, payload, engine_factory=factory)


def seed_experience(project, factory, clock, agent="claude-code"):
    base = {"session_id": "old", "cwd": str(project)}
    call(agent, "UserPromptSubmit", {**base, "prompt": "Fix the login bug where expired tokens are accepted"}, factory)
    steps = [("Edit", {"file_path": "src/auth.py"}, None), ("Bash", {"command": "pytest -q"}, None)]
    for index, (tool, arguments, error) in enumerate(steps):
        clock.advance(10)
        payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": f"old-{index}"}
        call(agent, "PreToolUse", payload, factory)
        call(agent, "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    call(agent, "Stop", base, factory)
    clock.advance(600)


def test_unapproved_project_is_not_captured_and_notifies_once(project, factory):
    payload = {"session_id": "s", "cwd": str(project), "hook_event_name": "SessionStart", "source": "startup"}
    first = json.loads(call("claude-code", "SessionStart", payload, factory))
    assert "not enabled" in first["systemMessage"]
    assert call("claude-code", "SessionStart", payload, factory) == ""
    call("claude-code", "UserPromptSubmit", {**payload, "prompt": "Fix the login bug with expired tokens"}, factory)
    engine = factory(project)
    assert engine.store.list("Task") == []


def test_claude_code_round_trip_injects_additional_context(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)
    output = call("claude-code", "UserPromptSubmit", {"session_id": "new", "cwd": str(project / "src"),
                                                       "prompt": "Fix login bug: expired tokens are still accepted"}, factory)
    data = json.loads(output)
    assert data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "src/auth.py" in data["hookSpecificOutput"]["additionalContext"]


def test_claude_code_failure_event_records_error_signature(project, factory, clock):
    approve(project)
    base = {"session_id": "s", "cwd": str(project)}
    call("claude-code", "UserPromptSubmit", {**base, "prompt": "Make the payment retry job idempotent please"}, factory)
    payload = {**base, "tool_name": "Bash", "tool_input": {"command": "pytest"}, "tool_use_id": "t1"}
    call("claude-code", "PreToolUse", payload, factory)
    call("claude-code", "PostToolUseFailure", {**payload, "error": "Exit code 1\nE   KeyError: 'retry_id'"}, factory)
    tool = factory(project).store.list("ToolCall")[0]
    assert tool.status == "failure" and tool.category == "test" and "KeyError" in tool.error_signature


def test_codex_failure_is_read_from_tool_response(project, factory):
    approve(project)
    base = {"session_id": "c", "cwd": str(project), "turn_id": "1"}
    call("codex", "UserPromptSubmit", {**base, "prompt": "Fix the flaky cache warmup on startup today"}, factory)
    payload = {**base, "tool_name": "Bash", "tool_input": {"command": "cargo test"}, "tool_use_id": "x"}
    call("codex", "PreToolUse", payload, factory)
    assert call("codex", "PostToolUse", {**payload, "tool_response": "Exit code: 101\nthread panicked"}, factory) == ""
    assert factory(project).store.list("ToolCall")[0].status == "failure"
    assert call("codex", "Stop", base, factory) == "", "Codex rejects plain-text output on Stop"


def test_cursor_delivers_pending_context_on_first_tool_result(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)
    base = {"conversation_id": "conv", "generation_id": "g", "workspace_roots": [str(project)], "cursor_version": "2.0"}
    prompt_out = call("cursor", "beforeSubmitPrompt", {**base, "prompt": "Fix login bug: expired tokens still accepted"}, factory)
    assert json.loads(prompt_out) == {"continue": True}, "beforeSubmitPrompt cannot inject context"
    payload = {**base, "tool_name": "Read", "tool_input": {"file_path": "src/auth.py"}, "tool_use_id": "r1"}
    assert json.loads(call("cursor", "preToolUse", payload, factory)) == {}, "never grant or deny permissions"
    first = json.loads(call("cursor", "postToolUse", {**payload, "tool_output": "{\"content\": \"...\"}"}, factory))
    assert "[OpenReflex]" in first["additional_context"]
    payload["tool_use_id"] = "r2"
    call("cursor", "preToolUse", payload, factory)
    assert json.loads(call("cursor", "postToolUse", {**payload, "tool_output": "{}"}, factory)) == {}


def test_cursor_running_claude_code_hooks_is_attributed_to_cursor(project, factory):
    approve(project)
    payload = {"conversation_id": "conv", "cursor_version": "2.0", "workspace_roots": [str(project)],
               "prompt": "Add rate limiting to the public search endpoint"}
    call("claude-code", "UserPromptSubmit", payload, factory)
    call("cursor", "beforeSubmitPrompt", payload, factory)
    tasks = factory(project).store.list("Task")
    assert len(tasks) == 1 and tasks[0].agent == "cursor"


def test_opencode_protocol(project, factory):
    approve(project)
    base = {"session_id": "o", "cwd": str(project)}
    call("opencode", "chat.message", {**base, "prompt": "Implement dark mode toggle in the settings page"}, factory)
    tool = {**base, "tool": "edit", "call_id": "k", "args": {"filePath": str(project / "src" / "theme.ts")}}
    call("opencode", "tool.before", tool, factory)
    assert json.loads(call("opencode", "tool.error", {**tool, "error": "Error: oldString not found"}, factory)) == \
        {"context": None, "notice": None}
    stored = factory(project).store.list("ToolCall")[0]
    assert stored.status == "failure" and stored.files == ["src/theme.ts"]


def test_safe_handle_never_raises(project):
    assert hooks.safe_handle("claude-code", "PostToolUse", "{not json") == ""
    assert json.loads(hooks.safe_handle("cursor", "beforeSubmitPrompt", "[]")) == {"continue": True}
    assert hooks.safe_handle("unknown-agent", "PostToolUse", "{}") == ""


@pytest.mark.parametrize("response, failed", [
    ({"stdout": "ok", "stderr": ""}, False),
    ({"exit_code": 2, "stderr": "boom"}, True),
    ({"isError": True, "content": []}, True),
    ("Exit code 0\nfine", False),
    ("Process exited with code 1", True),
])
def test_response_failure(response, failed):
    assert hooks.response_failure(response)[0] is failed


# Payload shapes below were captured from live codex-cli 0.154 sessions: shell results carry no exit code.
CODEX_FAILED_PYTEST = (
    "FF                                                                       [100%]\r\n"
    "================================== FAILURES ===================================\r\n"
    "E       assert (2024, 2, 15) == (2024, 3, 15)\r\n"
    "2 failed in 0.03s\r\n"
)


@pytest.mark.parametrize("command, response, success", [
    ("python -m pytest -q", CODEX_FAILED_PYTEST, False),
    ("python -m pytest -q", "..                                                   [100%]\r\n2 passed in 0.01s\r\n", True),
    ("Get-Content tests/test_dates.py", "def test_x():\n    assert parse('x') == 1  # 2 failed in 3 tries\n", True),
    ("pytset -q", "pytset : The term 'pytset' is not recognized as the name of a cmdlet, function", False),
    ("npm test", "Tests:       1 failed, 3 passed, 4 total", False),
])
def test_codex_shell_failures_are_read_from_output(command, response, success):
    event = hooks.normalize("codex", "PostToolUse", {"session_id": "s", "tool_name": "Bash",
                                                     "tool_input": {"command": command}, "tool_response": response})
    assert event.success is success


def test_claude_code_post_tool_use_output_is_not_reinterpreted():
    event = hooks.normalize("claude-code", "PostToolUse", {"session_id": "s", "tool_name": "Bash",
                                                           "tool_input": {"command": "python -m pytest -q"},
                                                           "tool_response": CODEX_FAILED_PYTEST})
    assert event.success is True, "Claude Code reports failures through PostToolUseFailure"


def test_codex_apply_patch_exit_code_zero_is_success():
    response = "Exit code: 0\nWall time: 2 seconds\nOutput:\nSuccess. Updated the following files:\nM dates.py\n"
    event = hooks.normalize("codex", "PostToolUse", {"session_id": "s", "tool_name": "apply_patch",
                                                     "tool_input": {"command": "*** Begin Patch\n*** Update File: dates.py\n"},
                                                     "tool_response": response})
    assert event.success is True


@pytest.mark.parametrize("tool_name", ["", None, ["Bash"], 7])
def test_tool_event_without_a_tool_name_records_nothing(project, factory, tool_name):
    approve(project)
    payload = {"session_id": "s", "cwd": str(project), "tool_name": tool_name, "tool_input": {"command": "ls"},
               "tool_use_id": "t1", "tool_response": {"stdout": "ok"}}
    assert call("claude-code", "PreToolUse", payload, factory) == ""
    assert call("claude-code", "PostToolUse", payload, factory) == ""
    engine = factory(project)
    assert engine.store.list("Task") == [] and engine.store.list("ToolCall") == []


def test_why_and_trace_survive_later_activity_without_a_prompt(project, factory, clock):
    approve(project)
    base = {"session_id": "planned", "cwd": str(project)}
    call("claude-code", "UserPromptSubmit", {**base, "prompt": "Fix the pricing bug where the SAVE15 coupon takes too little off"},
         factory)
    clock.advance(30)
    # A different session then runs a tool with no captured prompt, which creates an untracked task.
    other = {"session_id": "resumed", "cwd": str(project), "tool_name": "Read", "tool_input": {"file_path": "README.md"},
             "tool_use_id": "r1", "tool_response": {"content": "x"}}
    call("claude-code", "PreToolUse", other, factory)
    call("claude-code", "PostToolUse", other, factory)
    engine = factory(project)
    assert "No decision snapshot" not in engine.why() and "Recommendation" in engine.why()
    assert "START" in engine.trace()



def _hook_success(agent, base, tool_id, tool, arguments, factory, response=None):
    payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": tool_id}
    call(agent, "PreToolUse", payload, factory)
    return call(agent, "PostToolUse", {**payload, "tool_response": response or {"stdout": "ok"}}, factory)


def test_claude_hooks_reuse_runner_project_area_across_implementation_plan_and_followup(project, factory, clock):
    """Regression for the real runner transcript: hooks alone must learn and surface the project area."""
    approve(project)
    base = {"session_id": "runner", "cwd": str(project)}

    call(
        "claude-code",
        "UserPromptSubmit",
        {**base, "prompt": "Add GCP-native Bitbucket Kubernetes runner for quest-dev"},
        factory,
    )
    _hook_success(
        "claude-code", base, "tf-edit", "Edit", {"file_path": "terraform/config/runner.tf"}, factory
    )
    clock.advance(2)
    _hook_success(
        "claude-code", base, "helm-edit", "Edit", {"file_path": "helm/bitbucket-runner/Chart.yaml"}, factory
    )
    clock.advance(2)
    _hook_success(
        "claude-code", base, "helm-lint", "Bash", {"command": "helm lint helm/bitbucket-runner"}, factory
    )
    first_stop = json.loads(call("claude-code", "Stop", base, factory))
    assert "COMPLETE" in first_stop["systemMessage"]

    clock.advance(20)
    call(
        "claude-code",
        "UserPromptSubmit",
        {
            **base,
            "prompt": "No I want the complete implementation plan in very simple bullet points to be created and committed in a branch",
        },
        factory,
    )
    _hook_success(
        "claude-code",
        base,
        "plan-edit",
        "Write",
        {"file_path": "docs/bitbucket-runner-plan.md"},
        factory,
    )
    second_stop = json.loads(call(
        "claude-code",
        "Stop",
        {**base, "last_assistant_message": "Created the complete implementation plan and committed it on the branch."},
        factory,
    ))
    assert "COMPLETE" in second_stop["systemMessage"]

    clock.advance(20)
    third = json.loads(call(
        "claude-code",
        "UserPromptSubmit",
        {**base, "prompt": "Where is the implementation plan committed?"},
        factory,
    ))
    context = third["hookSpecificOutput"]["additionalContext"]
    assert "Reflex: Bitbucket runner work" in context
    assert "Project-area memory:" in context
    assert "inspect-first" not in context
    assert "test-first" not in context
