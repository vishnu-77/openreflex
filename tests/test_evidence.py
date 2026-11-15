"""metrics.evidence: what the pane shows about whether memory is used and checked.

Each number must mean exactly what its pane label says, so each is driven by real hook sequences.
"""
import re
from pathlib import Path

import pytest

from openreflex.engine import Engine
from openreflex.metrics import MIN_HOLDOUT_SIDE, _typical_change, evidence
from openreflex.project import approve
from openreflex.project_memory import read_state
from openreflex.reflex_index import EVIDENCE_REFRESH_SECONDS, refresh_evidence, sync_counts
from openreflex.store import Store

from .test_holdout_pipeline import holdout, run_task
from .test_hooks import call, seed_experience

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def test_outcomes_are_counted_per_evidence_level(project, factory, clock):
    approve(project)
    run_task(project, factory, clock, "checked")  # edits, then a passing check: check_passed
    base = {"session_id": "said", "cwd": str(project)}
    call("claude-code", "UserPromptSubmit", {**base, "prompt": "Rename the billing helper to match the new API"}, factory)
    payload = {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/billing.py"}, "tool_use_id": "b1"}
    call("claude-code", "PreToolUse", payload, factory)
    call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    factory(project).record_outcome("success", "renamed")  # no check after the edit: only the agent's word
    outcomes = evidence(factory(project))["outcomes"]
    assert outcomes == {"independently_verified": 0, "check_passed": 1, "agent_reported": 1, "inferred": 0,
                        "unknown": 0}


def test_recall_counts_shown_and_used_separately(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)  # touched src/auth.py
    said = run_task(project, factory, clock, "again", prompt="Fix login bug: expired tokens are still accepted")
    assert "[OpenReflex]" in said, "the seeded experience must be recalled for this test to mean anything"
    recall = evidence(factory(project))["recall"]
    # run_task also touches src/auth.py: the recalled file was used. No task went without recall, so no chance figure.
    assert recall == {"shown": 1, "checkable": 1, "used": 1, "chance": None}


def test_recall_shown_but_not_used_is_not_counted_as_used(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)
    base = {"session_id": "elsewhere", "cwd": str(project)}
    said = call("claude-code", "UserPromptSubmit", {**base, "prompt": "Fix login bug: expired tokens are still accepted"},
                factory)
    assert "[OpenReflex]" in said
    payload = {**base, "tool_name": "Read", "tool_input": {"file_path": "docs/unrelated.md"}, "tool_use_id": "u1"}
    call("claude-code", "PreToolUse", payload, factory)
    call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
    call("claude-code", "Stop", base, factory)
    assert evidence(factory(project))["recall"] == {"shown": 1, "checkable": 1, "used": 0, "chance": None}


def test_holdout_gives_no_figure_below_the_minimum(project, factory, clock, isolated_home):
    approve(project)
    holdout(isolated_home, 100)
    run_task(project, factory, clock, "held")
    holdout(isolated_home, 0)
    run_task(project, factory, clock, "shown")
    data = evidence(factory(project))["holdout"]
    assert (data["shown"], data["held_out"], data["min_side"]) == (1, 1, MIN_HOLDOUT_SIDE)
    assert data["tool_call_change"] is None


def test_evidence_reaches_the_state_file_the_pane_reads(project, isolated_home):
    approve(project)
    sync_counts(project)
    written = read_state(project)["evidence"]
    pane_types = (ROOT / "plugins/openreflex/types/index.d.ts").read_text(encoding="utf-8")
    body = re.search(r"export type Evidence = \{(.*?)\n\}", pane_types, re.S).group(1)
    assert set(re.findall(r"^  (\w+)\?:", body, re.M)) == set(written)
    for key, value in written.items():
        if isinstance(value, dict):
            nested = re.search(rf"^  {key}\?: \{{(.*?)\}}$", body, re.M).group(1)
            assert set(re.findall(r"(\w+)\?:", nested)) == set(value), key


def test_a_recall_naming_no_files_cannot_be_judged(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)
    engine = factory(project)
    for x in engine.store.list("Experience"):  # the recalled experience touched no file
        x.files = []
        engine.store.put(x)
    run_task(project, factory, clock, "again", prompt="Fix login bug: expired tokens are still accepted")
    recall = evidence(factory(project))["recall"]
    assert (recall["shown"], recall["checkable"], recall["used"]) == (1, 0, 0)


def test_chance_is_how_often_tasks_shown_nothing_touch_the_recalled_files(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)  # src/auth.py
    run_task(project, factory, clock, "again", prompt="Fix login bug: expired tokens are still accepted")
    # Two unrelated tasks shown nothing: one touches src/auth.py by chance, one does not.
    for session, path in (("lucky", "src/auth.py"), ("other", "docs/guide.md")):
        base = {"session_id": session, "cwd": str(project)}
        call("claude-code", "UserPromptSubmit", {**base, "prompt": f"Write the release notes for the {session} build please"},
             factory)
        payload = {**base, "tool_name": "Edit", "tool_input": {"file_path": path}, "tool_use_id": f"{session}-1"}
        call("claude-code", "PreToolUse", payload, factory)
        call("claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}}, factory)
        call("claude-code", "Stop", base, factory)
        clock.advance(600)
    recall = evidence(factory(project))["recall"]
    assert recall["used"] == 1 and recall["chance"] is not None and 0 < recall["chance"] < 1


def test_typical_change_has_a_95_percent_range_and_needs_both_sides():
    assert _typical_change([10] * 5, [20] * 5) == {"tool_call_change": None, "low": None, "high": None}
    shown = [8, 9, 10, 11, 12] * 6
    held = [16, 18, 20, 22, 24] * 6
    out = _typical_change(shown, held)
    assert out["low"] < out["tool_call_change"] < out["high"] < 0  # clearly fewer calls with OpenReflex
    same = _typical_change(shown, shown)
    assert same["tool_call_change"] == 0 and same["low"] < 0 < same["high"]  # no difference: the range spans zero


def test_stop_refreshes_evidence_at_most_every_few_minutes(project, isolated_home):
    approve(project)
    assert refresh_evidence(project, now=1_000.0) is True
    assert read_state(project)["evidence"]["tasks"] == 0
    assert refresh_evidence(project, now=1_000.0 + EVIDENCE_REFRESH_SECONDS - 1) is False
    assert refresh_evidence(project, now=1_000.0 + EVIDENCE_REFRESH_SECONDS) is True
