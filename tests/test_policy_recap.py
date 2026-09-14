import json

from openreflex import hooks
from openreflex.cli import build_parser
from openreflex.decision import render_recap
from openreflex.engine import Engine
from openreflex.models import Experience
from openreflex.policy import load_policy
from openreflex.project import approve
from openreflex.routing import classify, embed
from openreflex.store import Store

from .conftest import run_task
from .test_engine import FIX_SCRIPT


def test_policy_loads_packaged_defaults_and_project_overrides(project):
    default = load_policy(project)
    assert default.version == "1.0"
    assert default.boolean("visibility.show_start") is True
    assert default.tables("routing.strategies")

    (project / ".openreflex.toml").write_text(
        "[visibility]\nshow_start = false\n\n[score.weights]\nevidence = 1.0\n",
        encoding="utf-8",
    )
    configured = load_policy(project)
    assert configured.boolean("visibility.show_start") is False
    assert configured.number("score.weights.evidence") == 1.0
    assert configured.number("score.weights.confidence") == default.number("score.weights.confidence")


def test_start_recap_is_recorded_visible_once_and_explainable(engine):
    assert engine.prompt("claude-code", "s", "Fix the intermittent authentication refresh failure please") is None
    snapshots = engine.decision_snapshots()
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.phase == "start" and snapshot.visibility == "recap"
    assert 0 <= snapshot.reflex_score <= 100
    assert snapshot.policy_version == engine.policy.version

    notice = engine.take_notice("claude-code", "s")
    assert notice.startswith("↺ OpenReflex · ")
    assert "experiences" in notice and "calls" in notice and "context tokens" in notice
    assert engine.take_notice("claude-code", "s") is None

    why = engine.why()
    assert "OPENREFLEX / WHY" in why and "REFLEX" in why and "Policy" in why
    trace = engine.trace()
    assert "OPENREFLEX / TRACE" in trace and "START" in trace


def test_recap_reports_retrieved_experience_and_context_cost(engine, clock):
    description = "Fix expired authentication tokens still being accepted by the login check"
    prior = Experience(
        task_id="old-task",
        execution_id="old-execution",
        outcome_id="old-outcome",
        agent="claude-code",
        description=description,
        task_class=classify(description),
        strategy="test-first",
        status="success",
        elapsed_seconds=120,
        tool_calls=8,
        output_tokens_estimate=2400,
        files=["src/auth.py"],
        embedding=embed(description),
        created_at=clock(),
    )
    engine.store.put(prior)

    context = engine.prompt("claude-code", "new", description)
    assert context and "src/auth.py" in context
    snapshot = engine.decision_snapshots()[0]
    assert snapshot.evidence_count == 1
    assert snapshot.context_tokens > 0
    notice = engine.take_notice("claude-code", "new")
    assert "1 experiences" in notice and f"+{snapshot.context_tokens} context tokens" in notice


def test_completion_recap_shows_realised_path_cost_and_comparison(engine, clock):
    outcome, _ = run_task(
        engine,
        clock,
        "complete",
        "Fix the login bug where expired tokens are accepted",
        FIX_SCRIPT,
    )
    snapshot = engine.decision_snapshots(outcome.execution_id)[-1]
    recap = render_recap(snapshot)
    assert recap.startswith("↺ OpenReflex · COMPLETE")
    assert "success · test-first" in recap
    assert "5 calls" in recap
    assert "regret" in recap
    if snapshot.next_best_strategy:
        assert f"vs {snapshot.next_best_strategy}" in recap


def test_claude_hook_surfaces_recap_as_system_message(project, tmp_path, clock):
    approve(project)
    database = tmp_path / "recap-hooks.sqlite3"

    def factory(root):
        return Engine(root, Store(database), clock=clock)

    payload = {
        "session_id": "s",
        "cwd": str(project),
        "prompt": "Fix the intermittent authentication refresh failure please",
    }
    start = json.loads(hooks.handle("claude-code", "UserPromptSubmit", payload, engine_factory=factory))
    assert start["systemMessage"].startswith("↺ OpenReflex · ")
    assert "authentication refresh" not in start["systemMessage"]

    complete = json.loads(hooks.handle("claude-code", "Stop", {"session_id": "s", "cwd": str(project)},
                                       engine_factory=factory))
    assert complete["systemMessage"].startswith("↺ OpenReflex · COMPLETE")


def test_codex_remains_non_chatty_on_stop(project, tmp_path, clock):
    approve(project)
    database = tmp_path / "codex-recap.sqlite3"

    def factory(root):
        return Engine(root, Store(database), clock=clock)

    payload = {"session_id": "c", "cwd": str(project), "prompt": "Fix the intermittent cache refresh failure please"}
    hooks.handle("codex", "UserPromptSubmit", payload, engine_factory=factory)
    assert hooks.handle("codex", "Stop", {"session_id": "c", "cwd": str(project)}, engine_factory=factory) == ""


def test_cli_exposes_why_and_trace():
    parser = build_parser()
    assert parser.parse_args(["why"]).command == "why"
    assert parser.parse_args(["trace"]).command == "trace"


def test_trivial_prompts_get_no_recap(engine, clock):
    """A greeting that happens to trigger a tool call (e.g. a memory read) is not a task and must stay quiet."""
    assert engine.prompt("claude-code", "s", "Hi") is None
    assert engine.take_notice("claude-code", "s") is None
    read = ("Read", {"file_path": "MEMORY.md"})
    engine.tool_start("claude-code", "s", "t1", *read)
    clock.advance(2)
    engine.tool_end("claude-code", "s", "t1", *read, False, "file not found")
    engine.stop("claude-code", "s")
    assert engine.take_notice("claude-code", "s") is None
    assert all(item["visibility"] == "ambient" for item in engine.store.latest("claude-code", "s").decision_history)
