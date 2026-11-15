"""ADR 0001, decision 2 (memory lifecycle, "created"): memory comes only from work a person asked for.

Versions before 0.10.0 stored task notifications and subagent hand-backs as tasks. New ones are filtered at the
door; these tests hold every place that learns from or recalls experience to the same rule for the old records.
"""
import pytest

from openreflex.engine import Engine
from openreflex.models import is_harness_message
from openreflex.project import approve
from openreflex.reflexes import compile_for_experience
from openreflex.store import Store

from .test_holdout_pipeline import run_task

PROMPT = "Fix the login bug where expired tokens are still accepted by the API"
NOTIFICATION = "<task-notification> <status>completed</status> Fix the login bug where expired tokens are still accepted"


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def make_legacy_machine_record(engine: Engine, session: str) -> None:
    """Rewrite a stored task the way versions before 0.10.0 recorded a task notification."""
    task = next(t for t in engine.store.list("Task") if t.session_id == session)
    task.description, task.substantial = NOTIFICATION, True
    engine.store.put(task)
    for x in engine.store.list("Experience"):
        if x.task_id == task.id:
            x.description = NOTIFICATION
            engine.store.put(x)


def test_harness_messages_are_recognised_with_leading_space():
    assert is_harness_message("  <task-notification> x")
    assert is_harness_message('<agent-message from="a1"> report')
    assert not is_harness_message("Fix the <task-notification> parser in the queue worker")


def test_a_legacy_machine_record_adds_no_reflex_support(project, factory, clock):
    approve(project)
    run_task(project, factory, clock, "person")
    run_task(project, factory, clock, "machine")
    engine = factory(project)
    make_legacy_machine_record(engine, "machine")
    person = next(x for x in engine.store.list("Experience") if x.description != NOTIFICATION)
    reflex = compile_for_experience(engine.store, person, clock())
    assert reflex.support_count == 1


def test_a_legacy_machine_record_is_never_recalled(project, factory, clock):
    approve(project)
    run_task(project, factory, clock, "machine")
    engine = factory(project)
    make_legacy_machine_record(engine, "machine")
    preview = factory(project).preview(PROMPT)
    assert "task-notification" not in preview
    assert "0 similar past task(s) here" in preview  # the only stored experience is the machine record


def test_a_person_task_with_the_same_words_is_still_recalled(project, factory, clock):
    # Control for the test above: the filter removes machine records, not recall itself.
    approve(project)
    run_task(project, factory, clock, "person")
    assert "1 similar past task(s) here" in factory(project).preview(PROMPT)
