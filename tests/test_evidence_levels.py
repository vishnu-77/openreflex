"""ADR 0001, decision 1: every outcome records how strong its evidence is, and unlike evidence is never merged.

observed < agent_reported < check_passed < independently_verified. "Verified" means check_passed or stronger;
an agent's own report never counts as verified, and a passing check is not relabelled "correct".
"""
import pytest

from openreflex.engine import Engine
from openreflex.models import Outcome, evidence_level_of, is_verified
from openreflex.project import approve
from openreflex.store import Store

from .test_holdout_pipeline import run_task
from .test_hooks import call

PROMPT = "Fix the login bug where expired tokens are still accepted by the API"


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def steps(project, factory, clock, session, calls, prompt=PROMPT, stop=True):
    """Run a task of (tool, arguments, error-or-None) calls through the real hooks."""
    base = {"session_id": session, "cwd": str(project)}
    call("claude-code", "UserPromptSubmit", {**base, "prompt": prompt}, factory)
    for index, (tool, arguments, error) in enumerate(calls):
        clock.advance(20)
        payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": f"{session}-{index}"}
        call("claude-code", "PreToolUse", payload, factory)
        if error:
            call("claude-code", "PostToolUseFailure", {**payload, "error": error}, factory)
        else:
            call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    if stop:
        call("claude-code", "Stop", base, factory)
        clock.advance(600)


def outcome_of(factory, project, session) -> Outcome:
    engine = factory(project)
    execution = engine.store.latest("claude-code", session)
    return engine.store.get("out-" + execution.id)


EDIT = ("Edit", {"file_path": "src/auth.py"}, None)
TEST_PASSES = ("Bash", {"command": "pytest -q"}, None)
TEST_FAILS = ("Bash", {"command": "pytest -q"}, "E   AssertionError: expired token accepted")


def test_a_check_seen_passing_after_the_last_edit_is_check_passed(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [EDIT, TEST_PASSES])
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("success", "check_passed")
    assert is_verified(outcome) and outcome.verified


def test_a_failing_last_check_is_observed_and_not_verified(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [EDIT, TEST_FAILS])
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("failure", "observed")
    assert not is_verified(outcome)


def test_no_check_after_the_last_edit_is_observed_and_unknown(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [TEST_PASSES, EDIT])  # the check ran before the edit: it proves nothing
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("unknown", "observed")


def test_an_agent_report_is_agent_reported_and_not_verified(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [EDIT], stop=False)
    factory(project).record_outcome("success", "pytest: 12 passed")
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("success", "agent_reported")
    assert not is_verified(outcome) and not outcome.verified


def test_an_agent_report_agreeing_with_a_passing_check_keeps_the_stronger_level(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [EDIT, TEST_PASSES])
    engine = factory(project)
    engine.record_outcome("success", "done", engine.store.latest("claude-code", "s").id)
    assert evidence_level_of(outcome_of(factory, project, "s")) == "check_passed"


def test_an_agent_failure_report_overrides_a_passing_check(project, factory, clock):
    # A passing check proves the check passed, not that the task is done: the agent may know it is not.
    approve(project)
    steps(project, factory, clock, "s", [EDIT, TEST_PASSES])
    engine = factory(project)
    engine.record_outcome("failure", "the endpoint still returns 200", engine.store.latest("claude-code", "s").id)
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("failure", "agent_reported")
    assert not is_verified(outcome)


def test_a_later_stop_does_not_replace_an_agent_report_with_weaker_evidence(project, factory, clock):
    approve(project)
    steps(project, factory, clock, "s", [EDIT], stop=False)
    factory(project).record_outcome("success", "done")
    # The agent keeps working after its report (no check), so the task is finalized again from the calls seen:
    # inference alone would now say "unknown", which must not replace the report.
    base = {"session_id": "s", "cwd": str(project)}
    payload = {**base, "tool_name": "Read", "tool_input": {"file_path": "README.md"}, "tool_use_id": "s-after"}
    call("claude-code", "PreToolUse", payload, factory)
    call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    call("claude-code", "Stop", base, factory)
    outcome = outcome_of(factory, project, "s")
    assert (outcome.status, evidence_level_of(outcome)) == ("success", "agent_reported")
    assert outcome.evidence == "done"


@pytest.mark.parametrize(("verified", "level"), [(True, "agent_reported"), (False, "observed")])
def test_outcomes_written_before_levels_are_read_conservatively(verified, level):
    # Before evidence levels, only the agent's own record_outcome call set verified=True.
    legacy = Outcome(execution_id="e", status="success", evidence="", verified=verified, elapsed_seconds=1.0,
                     tool_calls=1, failures=0, output_tokens_estimate=0)
    assert evidence_level_of(legacy) == level
    assert not is_verified(legacy)


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError):
        Outcome(execution_id="e", status="success", evidence="", evidence_level="trust me", elapsed_seconds=1.0,
                tool_calls=1, failures=0, output_tokens_estimate=0)


def test_reflexes_count_checks_seen_passing(project, factory, clock):
    approve(project)
    for index in range(4):
        steps(project, factory, clock, f"checked-{index}", [EDIT, TEST_PASSES])
    assert max(r.verified_count for r in factory(project).store.list_reflexes()) == 4


def test_reflexes_do_not_count_agent_reports_as_verified(project, factory, clock):
    approve(project)
    for index in range(4):
        steps(project, factory, clock, f"said-{index}", [EDIT], stop=False)
        factory(project).record_outcome("success", "done")
        call("claude-code", "Stop", {"session_id": f"said-{index}", "cwd": str(project)}, factory)
    reflexes = factory(project).store.list_reflexes()
    assert reflexes and max(r.verified_count for r in reflexes) == 0
    assert max(r.success_count for r in reflexes) == 4  # the reports still count as successes, just not verified


def test_run_task_helper_now_ends_check_passed(project, factory, clock):
    # The shared helper edits then runs a passing check: other suites rely on it being verified evidence.
    approve(project)
    run_task(project, factory, clock, "helper")
    assert evidence_level_of(outcome_of(factory, project, "helper")) == "check_passed"
