"""The holdout is OpenReflex's only unconfounded measure of its own effect.

These tests drive real hook sequences end to end and check the whole chain: assignment, silence, and counting
in `openreflex status`. `openreflex status` showed n=0/0 on every real project, so each link is tested on its own.
"""
import pytest

from openreflex.engine import Engine
from openreflex.metrics import project_metrics
from openreflex.project import approve
from openreflex.store import Store

from .test_hooks import call

PROMPT = "Fix the login bug where expired tokens are still accepted by the API"


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def holdout(isolated_home, percent: int) -> None:
    (isolated_home / "config.toml").write_text(f"[evaluation]\nholdout_percent = {percent}\n", encoding="utf-8")


def run_task(project, factory, clock, session: str, prompt: str = PROMPT) -> str:
    base = {"session_id": session, "cwd": str(project)}
    said = call("claude-code", "UserPromptSubmit", {**base, "prompt": prompt}, factory)
    for index, (tool, arguments) in enumerate([("Grep", {"pattern": "expired"}), ("Read", {"file_path": "src/auth.py"}),
                                               ("Edit", {"file_path": "src/auth.py"}), ("Bash", {"command": "pytest -q"})]):
        clock.advance(20)
        payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": f"{session}-{index}"}
        call("claude-code", "PreToolUse", payload, factory)
        call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    call("claude-code", "Stop", base, factory)
    clock.advance(600)
    return said


def test_a_held_out_task_is_stored_as_held_out(project, factory, clock, isolated_home):
    approve(project)
    holdout(isolated_home, 100)
    run_task(project, factory, clock, "s1")
    executions = factory(project).store.list("Execution")
    assert executions and all(e.holdout for e in executions)


def test_status_counts_held_out_tasks(project, factory, clock, isolated_home):
    approve(project)
    holdout(isolated_home, 100)
    run_task(project, factory, clock, "s1")
    data = project_metrics(factory(project), now=clock())
    assert data["holdout"]["held_out"]["n"] == 1


def test_status_compares_shown_and_held_out_tasks(project, factory, clock, isolated_home):
    approve(project)
    holdout(isolated_home, 100)
    run_task(project, factory, clock, "held")
    holdout(isolated_home, 0)
    run_task(project, factory, clock, "shown")
    data = project_metrics(factory(project), now=clock())
    assert (data["holdout"]["shown"]["n"], data["holdout"]["held_out"]["n"]) == (1, 1)


def test_status_ignores_machine_messages_recorded_by_older_versions(project, factory, clock, isolated_home):
    # Before 0.10.0, task notifications and subagent hand-backs were stored as substantial tasks of their own.
    approve(project)
    run_task(project, factory, clock, "person")
    run_task(project, factory, clock, "machine", prompt="ignored: rewritten below as an old record")
    engine = factory(project)
    machine = next(t for t in engine.store.list("Task") if t.session_id == "machine")
    machine.description = "<task-notification> <task-id>b1</task-id> <status>completed</status> background job finished"
    machine.substantial = True
    engine.store.put(machine)

    data = project_metrics(factory(project), now=clock())
    assert data["engagement"]["substantial_tasks"] == 1
    assert data["engagement"]["experiences"] == 1
    assert data["outcomes"]["known"] <= 1
