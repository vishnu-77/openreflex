"""metrics.evidence: what the pane shows about whether memory is used and checked.

Each number must mean exactly what its pane label says, so each is driven by real hook sequences.
"""
import re
from pathlib import Path

import pytest

from openreflex.engine import Engine
from openreflex.metrics import MIN_HOLDOUT_SIDE, evidence
from openreflex.project import approve
from openreflex.project_memory import read_state
from openreflex.reflex_index import sync_counts
from openreflex.store import Store

from .test_holdout_pipeline import holdout, run_task
from .test_hooks import call, seed_experience

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def test_outcomes_separate_verified_from_inferred(project, factory, clock):
    approve(project)
    run_task(project, factory, clock, "inferred")
    run_task(project, factory, clock, "checked")
    engine = factory(project)
    latest = engine.store.latest("claude-code", "checked")
    engine.record_outcome("success", "pytest -q: 12 passed", latest.id)
    outcomes = evidence(factory(project))["outcomes"]
    assert outcomes["verified"] == 1
    assert outcomes["verified"] + outcomes["inferred"] + outcomes["unknown"] == 2


def test_recall_counts_shown_and_used_separately(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)  # touched src/auth.py
    said = run_task(project, factory, clock, "again", prompt="Fix login bug: expired tokens are still accepted")
    assert "[OpenReflex]" in said, "the seeded experience must be recalled for this test to mean anything"
    recall = evidence(factory(project))["recall"]
    # run_task also touches src/auth.py: the recalled file was used.
    assert recall == {"shown": 1, "used": 1}


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
    assert evidence(factory(project))["recall"] == {"shown": 1, "used": 0}


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
