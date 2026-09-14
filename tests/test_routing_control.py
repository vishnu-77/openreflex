from openreflex.models import Experience
from openreflex.routing import Limits, budget_for, candidates, dominates, limits_from_env

from .test_mcp_metrics_benchmark import tool_text


def experience(strategy, status="success", calls=18, regret=None, alerts=()):
    return Experience(task_id="t", execution_id="e", outcome_id="o", description="Fix the webhook signature check",
                      task_class="debug", strategy=strategy, status=status, elapsed_seconds=540, tool_calls=calls,
                      output_tokens_estimate=6000, estimated_regret=regret, alerts=list(alerts), embedding=[],
                      created_at=0)


def test_dominated_paths_are_marked_and_never_recommended():
    paths = candidates("t", "debug", [])
    by_strategy = {p.strategy: p for p in paths}
    # With no evidence, test-first is at least as good as incremental on every objective for a debug task.
    assert by_strategy["incremental"].dominated_by == "test-first"
    assert dominates(by_strategy["test-first"], by_strategy["incremental"])
    assert by_strategy["inspect-first"].dominated_by is None and by_strategy["test-first"].dominated_by is None
    assert paths[0].strategy == "test-first" and paths[-1].strategy == "incremental"


def test_limits_select_a_path_that_fits_and_cap_the_budget():
    limits = Limits(tool_calls=15)
    paths = candidates("t", "debug", [], limits)
    assert paths[0].strategy == "inspect-first" and paths[0].within_limits
    assert not next(p for p in paths if p.strategy == "test-first").within_limits
    budget = budget_for(paths[0], limits)
    assert budget.tool_calls == 15 and budget.source == "limit"
    assert budget_for(paths[0]).source == "estimated" and budget_for(paths[0]).tool_calls > 15


def test_nothing_fits_the_limits_so_the_smallest_overrun_leads():
    paths = candidates("t", "debug", [], Limits(tool_calls=5))
    assert not any(p.within_limits for p in paths) and paths[0].strategy == "inspect-first"


def test_budget_limits_from_environment(monkeypatch):
    monkeypatch.setenv("OPENREFLEX_BUDGET", "calls=40, minutes=20,tokens=60000,bogus=3,calls=x,tokens=-1")
    assert limits_from_env() == Limits(seconds=1200, tool_calls=40, context_tokens=60000)
    monkeypatch.setenv("OPENREFLEX_BUDGET", "")
    assert limits_from_env() == Limits()


def test_budget_tightens_as_evidence_accumulates():
    fresh = candidates("t", "debug", [])[0]
    seasoned = candidates("t", "debug", [experience("test-first", calls=20) for _ in range(9)])[0]
    assert seasoned.uncertainty < fresh.uncertainty
    assert budget_for(seasoned).tool_calls < 2.5 * seasoned.tool_calls <= budget_for(fresh).tool_calls * 1.2


def test_regret_and_detours_feed_back_into_routing():
    clean = {p.strategy: p for p in candidates("t", "debug", [experience("test-first", regret=0.0) for _ in range(4)])}
    costly = {p.strategy: p for p in candidates("t", "debug", [
        experience("test-first", regret=0.3, alerts=["failure_loop"]) for _ in range(4)])}
    assert costly["test-first"].expected_regret > clean["test-first"].expected_regret == 0
    assert costly["test-first"].risk > clean["test-first"].risk
    assert costly["test-first"].score < clean["test-first"].score


def test_context_shows_budget_and_dominated_alternatives(engine):
    text = engine.preview("Fix the flaky payment webhook signature verification")
    assert "Budget: ~45 tool calls" in text and "incremental (dominated by test-first)" in text


def read(i):
    return ("Read", {"file_path": f"src/payments/part{i}.py"})


def test_stalled_path_gets_a_pivot_recommendation(engine, clock):
    engine.prompt("claude-code", "s1", "Fix the flaky payment webhook signature verification")
    edit = ("Edit", {"file_path": "src/payments/webhook.py", "old_string": "a", "new_string": "b"})
    engine.tool_start("claude-code", "s1", "e1", *edit)
    engine.tool_end("claude-code", "s1", "e1", *edit, True, None, 100)
    messages = []
    for i in range(16):
        clock.advance(20)
        engine.tool_start("claude-code", "s1", f"r{i}", *read(i))
        messages.append(engine.tool_end("claude-code", "s1", f"r{i}", *read(i), True, None, 800))
    alerts = [m for m in messages if m]
    assert len(alerts) == 1 and "without a successful edit or check" in alerts[0]
    # Editing before any check reads as inspect-first; stalled reading after it points to the untried test-first.
    assert "Recommendation: pivot to test-first" in alerts[0]
    assert engine.store.latest("claude-code", "s1").verdicts[0].startswith("pivot:inspect-first>test-first@")


def test_a_stalled_proven_path_can_still_pivot_to_an_alternative_it_dominated_at_planning(engine, clock):
    from .conftest import run_task
    fix = [("Bash", {"command": "python -m pytest -q"}, False, "E   AssertionError: expired token accepted"),
           ("Edit", {"file_path": "src/auth/session.py", "old_string": "a", "new_string": "b"}, True, None),
           ("Bash", {"command": "python -m pytest -q"}, True, None)]
    for i in range(3):
        run_task(engine, clock, f"s{i}", f"Fix the login bug where expired tokens are accepted ({i})", fix)
        clock.advance(3600)
    engine.prompt("claude-code", "s9", "Fix expired tokens still accepted by the login check")
    plan = {p.strategy: p for p in engine.store.list("CandidatePath", "task_id", engine.store.latest("claude-code", "s9").task_id)}
    assert plan["inspect-first"].dominated_by == "test-first"
    messages = []
    for i in range(8):
        clock.advance(200)
        cmd = ("Bash", {"command": f"python -m pytest -q -k case{i}"})
        engine.tool_start("claude-code", "s9", f"t{i}", *cmd)
        messages.append(engine.tool_end("claude-code", "s9", f"t{i}", *cmd, False, f"E   KeyError: case {i}"))
    assert any("Recommendation: pivot to inspect-first" in m for m in messages if m), [m for m in messages if m]


def test_early_failures_advise_continuing_not_abandoning_the_path(engine, clock):
    engine.prompt("claude-code", "s1", "Fix the flaky payment webhook signature verification")
    messages = []
    for i in range(3):
        clock.advance(20)
        cmd = ("Bash", {"command": f"python -m pytest tests/test_webhook.py -k sig{i}"})
        engine.tool_start("claude-code", "s1", f"t{i}", *cmd)
        messages.append(engine.tool_end("claude-code", "s1", f"t{i}", *cmd, False, "E   ValueError: bad signature"))
    assert messages[:2] == [None, None] and "Recommendation: continue" in messages[2]


def test_spent_budget_with_nothing_working_ends_in_one_stop_recommendation(engine, clock, monkeypatch):
    monkeypatch.setenv("OPENREFLEX_BUDGET", "calls=20")
    engine.prompt("claude-code", "s1", "Fix the flaky payment webhook signature verification")
    messages = []
    for i in range(40):
        clock.advance(200)  # past the alert cooldown each time
        cmd = ("Bash", {"command": f"python -m pytest tests/test_webhook.py -k case{i}"})
        engine.tool_start("claude-code", "s1", f"t{i}", *cmd)
        messages.append(engine.tool_end("claude-code", "s1", f"t{i}", *cmd, False, f"E   ValueError: bad case {i}"))
    said = [m for m in messages if m]
    pivots = [i for i, m in enumerate(said) if "Recommendation: pivot" in m]
    stops = [i for i, m in enumerate(said) if "Recommendation: stop" in m]
    assert pivots and len(stops) == 1 and pivots[-1] < stops[0], said
    assert "ask the user how to proceed" in said[stops[0]]
    execution = engine.store.latest("claude-code", "s1")
    assert execution.budget_source == "limit" and execution.budget_tool_calls == 20
    outcome = engine.stop("claude-code", "s1")
    assert any(v.startswith("stop@") for v in engine.store.get("exp-" + outcome.execution_id).verdicts)


def test_long_reading_is_not_over_the_time_budget(engine, clock):
    engine.prompt("claude-code", "s1", "Explain how the payment webhook verification works end to end")
    messages = []
    for i in range(25):
        clock.advance(90)
        engine.tool_start("claude-code", "s1", f"r{i}", *read(i))
        messages.append(engine.tool_end("claude-code", "s1", f"r{i}", *read(i), True, None, 800))
    assert not any(messages)


def test_mcp_limits_and_progress_check(project):
    from openreflex.mcp_server import build_server
    from openreflex.project import approve
    approve(project)
    server = build_server(project)
    context = tool_text(server, "get_execution_context", {"task": "Fix the login redirect loop after logout",
                                                          "max_tool_calls": 15})
    assert "Budget: ~15 tool calls" in context and "(your limit)" in context and "over the limits" in context
    assert "Suggested path: inspect-first" in context
    assert "limits must be positive" in tool_text(server, "get_execution_context", {"task": "x y z w v", "max_minutes": 0})
    progress = tool_text(server, "check_progress", {})
    assert progress.startswith("Recommendation: continue (no signs of trouble)") and "Marginal value" in progress
