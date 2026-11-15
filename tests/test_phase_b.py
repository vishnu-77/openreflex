"""ADR 0001, Phase B (revised by evidence): recall what changes the agent's next action, when it can act on it.

Replays on real projects showed file pointers recalled by prompt wording named the wrong files (0 of 11 hits on the
largest project), while files earlier tasks worked on together with the first file a task touches hit 4 of 7.
So prompt-time injection carries only specific lessons, and file pointers fire on the first file touched.
"""
import json

import pytest

from openreflex.engine import Engine
from openreflex.metrics import evidence
from openreflex.project import approve
from openreflex.store import Store

from .test_holdout_pipeline import holdout
from .test_hooks import call, seed_experience


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def said(output: str) -> str:
    """The context a hook handed to the model; a status-only message (systemMessage) hands it nothing."""
    return (json.loads(output).get("hookSpecificOutput") or {}).get("additionalContext", "") if output else ""


def task(project, factory, clock, session, prompt, calls):
    """Run a task of (tool, arguments) calls that all succeed; returns what each hook said, by event."""
    base = {"session_id": session, "cwd": str(project)}
    out = {"prompt": said(call("claude-code", "UserPromptSubmit", {**base, "prompt": prompt}, factory)), "tools": []}
    for index, (tool, arguments) in enumerate(calls):
        clock.advance(20)
        payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": f"{session}-{index}"}
        call("claude-code", "PreToolUse", payload, factory)
        out["tools"].append(said(call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}},
                                      factory)))
    call("claude-code", "Stop", base, factory)
    clock.advance(600)
    return out


READ_AUTH = ("Read", {"file_path": "src/auth.py"})
EDIT_AUTH = ("Edit", {"file_path": "src/auth.py"})
EDIT_TEST = ("Edit", {"file_path": "tests/test_auth.py"})
EDIT_SESSION = ("Edit", {"file_path": "src/session.py"})
PYTEST = ("Bash", {"command": "pytest -q"})
LOGIN = "Fix the login bug where expired tokens are still accepted by the API"


def test_a_matched_reflex_alone_injects_nothing(project, factory, clock):
    approve(project)
    for index in range(3):  # repeated clean successes: a Reflex forms, but there is no failure to learn from
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, PYTEST])
    out = task(project, factory, clock, "new", LOGIN, [])
    assert out["prompt"] == "", "a generic procedure is not injected"
    engine = factory(project)
    context = next(c for c in engine.store.list("Context")
                   if c.task_id == engine.store.latest("claude-code", "new").task_id)
    assert context.reflex_id is not None and not context.injected  # still matched, kept internal


def test_a_specific_lesson_is_still_injected_without_the_procedure(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)  # a failing test fixed by an edit: a resolution lesson
    out = said(call("claude-code", "UserPromptSubmit", {"session_id": "new", "cwd": str(project),
                                                        "prompt": "Fix login bug: expired tokens are still accepted"},
                    factory))
    assert out.startswith("[OpenReflex]") and "Lessons:" in out
    assert "Procedure:" not in out and "Reflex:" not in out


def test_the_first_file_points_to_files_worked_on_together_with_it(project, factory, clock):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    task(project, factory, clock, "other", "Tidy the session store and its expiry handling code", [EDIT_SESSION])
    out = task(project, factory, clock, "new", "Make the token refresh endpoint honour the clock skew", [READ_AUTH, EDIT_TEST])
    pointer = out["tools"][0]
    assert pointer.startswith("[OpenReflex]") and "src/auth.py" in pointer
    assert "tests/test_auth.py (2 tasks)" in pointer and "src/session.py" not in pointer
    assert out["tools"][1] == "", "only the first file a task touches triggers a pointer"


def test_no_pointer_for_a_file_with_no_history(project, factory, clock):
    approve(project)
    task(project, factory, clock, "s0", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    out = task(project, factory, clock, "new", "Add a health check endpoint for the load balancer", [EDIT_SESSION])
    assert out["tools"] == [""]


def test_held_out_tasks_get_no_pointer(project, factory, clock, isolated_home):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    holdout(isolated_home, 100)
    out = task(project, factory, clock, "held", "Make the token refresh endpoint honour the clock skew", [READ_AUTH])
    assert out["tools"] == [""]


def test_machine_records_do_not_feed_pointers(project, factory, clock):
    approve(project)
    task(project, factory, clock, "s0", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    engine = factory(project)
    for x in engine.store.list("Experience"):  # rewrite it as a pre-0.10.0 task notification
        x.description = "<task-notification> background job finished"
        engine.store.put(x)
    out = task(project, factory, clock, "new", "Make the token refresh endpoint honour the clock skew", [READ_AUTH])
    assert out["tools"] == [""]


def test_evidence_counts_pointers_shown_and_used(project, factory, clock):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    task(project, factory, clock, "used", "Make the token refresh endpoint honour the clock skew", [READ_AUTH, EDIT_TEST])
    task(project, factory, clock, "ignored", "Log the token refresh failures with their request id", [READ_AUTH])
    # s1 is pointed from s0 and edits tests/test_auth.py (used); "used" does too; "ignored" touches nothing pointed.
    assert evidence(factory(project))["pointers"] == {"shown": 3, "used": 2, "held_out": 0, "held_out_used": 0}


def test_held_out_tasks_record_what_they_would_have_been_shown(project, factory, clock, isolated_home):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    holdout(isolated_home, 100)
    task(project, factory, clock, "held", "Make the token refresh endpoint honour the clock skew", [READ_AUTH, EDIT_TEST])
    pointers = evidence(factory(project))["pointers"]
    assert (pointers["held_out"], pointers["held_out_used"]) == (1, 1)  # touched the file anyway, never told
