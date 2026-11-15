"""ADR 0001, decision 2 (memory lifecycle, "deleted"): forgetting an experience removes its influence from every
derived Reflex, ranking and index, by recomputing from the evidence that remains. Forgetting again changes nothing.
"""
import pytest

from openreflex.engine import Engine
from openreflex.metrics import evidence
from openreflex.project_memory import load_snapshot
from openreflex.reflex_index import reinforce_latest_execution

from .conftest import run_task
from .test_engine import FIX_SCRIPT
from .test_reflex_index import _project_with_auth

PROMPT = "Fix the login bug where expired tokens are accepted"


def auth_support(project) -> dict:
    return next(item for item in load_snapshot(project)["indexed_files"] if item["path"] == "src/auth.py")


def task(project, clock, session, prompt=PROMPT):
    engine = Engine(project, clock=clock)
    try:
        outcome, _ = run_task(engine, clock, session, prompt, FIX_SCRIPT)
        experience = engine.store.find("Experience", execution_id=outcome.execution_id)[0]
    finally:
        engine.close()
    reinforce_latest_execution(project, "claude-code", session)
    clock.advance(600)
    return experience


def forget(project, clock, experience_id):
    engine = Engine(project, clock=clock)
    try:
        return engine.forget_experience(experience_id)
    finally:
        engine.close()


def reflexes(project, clock):
    engine = Engine(project, clock=clock)
    try:
        return engine.store.list_reflexes()
    finally:
        engine.close()


@pytest.fixture
def auth_project(project):
    _project_with_auth(project)
    return project


def test_forgetting_removes_the_experience_from_every_reflex(auth_project, clock):
    first, second = task(auth_project, clock, "s1"), task(auth_project, clock, "s2")
    before = {r.id: r for r in reflexes(auth_project, clock)}
    assert before and all(r.support_count == 2 for r in before.values() if first.id in r.evidence_ids)

    forget(auth_project, clock, first.id)
    after = reflexes(auth_project, clock)
    assert after, "the remaining experience still supports its Reflexes"
    for reflex in after:
        assert first.id not in reflex.evidence_ids
        assert reflex.support_count == 1 and reflex.success_count == 1 and reflex.verified_count == 1
        assert second.id in reflex.evidence_ids


def test_forgetting_the_last_experience_of_a_family_removes_its_reflex(auth_project, clock):
    only = task(auth_project, clock, "s1")
    assert reflexes(auth_project, clock)
    forget(auth_project, clock, only.id)
    assert reflexes(auth_project, clock) == []


def test_forgetting_retracts_file_support(auth_project, clock):
    first = task(auth_project, clock, "s1")
    task(auth_project, clock, "s2")
    assert (auth_support(auth_project)["observations"], auth_support(auth_project)["verified_successes"]) == (2, 2)
    forget(auth_project, clock, first.id)
    support = auth_support(auth_project)
    assert (support["observations"], support["successful_outcomes"], support["verified_successes"]) == (1, 1, 1)


def test_later_recall_records_stop_pointing_at_a_forgotten_experience(auth_project, clock):
    seed = task(auth_project, clock, "s1")
    task(auth_project, clock, "s2")  # recalls the seed
    engine = Engine(auth_project, clock=clock)
    try:
        assert any(seed.id in c.experience_ids for c in engine.store.list("Context"))
    finally:
        engine.close()
    forget(auth_project, clock, seed.id)
    engine = Engine(auth_project, clock=clock)
    try:
        assert not any(seed.id in c.experience_ids for c in engine.store.list("Context"))
        assert evidence(engine)["recall"]["shown"] == 0
    finally:
        engine.close()


def test_forgetting_twice_changes_nothing_the_second_time(auth_project, clock):
    first = task(auth_project, clock, "s1")
    task(auth_project, clock, "s2")
    forget(auth_project, clock, first.id)
    state = ([(r.id, r.support_count) for r in reflexes(auth_project, clock)], auth_support(auth_project)["observations"])
    with pytest.raises(ValueError):
        forget(auth_project, clock, first.id)
    assert ([(r.id, r.support_count) for r in reflexes(auth_project, clock)],
            auth_support(auth_project)["observations"]) == state


def test_relearning_after_forgetting_starts_from_the_remaining_evidence(auth_project, clock):
    first = task(auth_project, clock, "s1")
    forget(auth_project, clock, first.id)
    again = task(auth_project, clock, "s2")
    for reflex in reflexes(auth_project, clock):
        assert reflex.evidence_ids == [again.id] and reflex.support_count == 1
    assert auth_support(auth_project)["observations"] == 1
