from openreflex.engine import UNTRACKED, is_substantial

from .conftest import run_task

TEST = ("Bash", {"command": "python -m pytest tests/test_auth.py -q"})
EDIT = ("Edit", {"file_path": "src/auth.py", "old_string": "a", "new_string": "b"})
READ = ("Read", {"file_path": "src/auth.py"})
GREP = ("Grep", {"pattern": "login"})


def step(tool, success=True, error=None):
    return (tool[0], tool[1], success, error)


FIX_SCRIPT = [step(GREP), step(READ), step(TEST, False, "E   AssertionError: expired token accepted"),
              step(EDIT), step(TEST)]


def test_substantial_prompt_detection():
    assert is_substantial("Fix the login bug where expired tokens are accepted")
    assert not is_substantial("yes please continue")
    assert not is_substantial("/compact")
    assert is_substantial("yes, and also refactor the payment module to use the new client")


def test_first_task_captures_full_trajectory_without_injecting(engine, clock):
    outcome, messages = run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted", FIX_SCRIPT)
    assert messages[0] is None, "nothing to inject without prior experience"
    assert outcome.status == "success" and not outcome.verified
    assert outcome.tool_calls == 5 and outcome.failures == 1
    assert outcome.chosen_strategy == "test-first"
    experience = engine.store.get("exp-" + outcome.execution_id)
    assert experience.files[0] == "src/auth.py"
    kinds = {lesson.kind for lesson in engine.store.list("Lesson")}
    assert {"strategy", "files", "resolution"} <= kinds
    # The failing test is linked to the edit that fixed it.
    resolved = engine.store.edges(relation="resolved_by")
    assert len(resolved) == 1 and engine.store.get(resolved[0]["target"]).category == "edit"


def test_similar_task_receives_execution_context_with_lessons_and_files(engine, clock):
    run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted", FIX_SCRIPT)
    clock.advance(3600)
    context = engine.prompt("codex", "s2", "Fix login bug: expired refresh tokens are still accepted")
    assert context is not None
    assert "similar past task" in context and "src/auth.py" in context
    assert "expired token accepted" in context
    assert "test-first" not in context
    execution = engine.store.latest("codex", "s2")
    stored = engine.store.list("Context", "task_id", execution.task_id)[0]
    assert stored.injected and stored.experience_ids, "cross-agent, cross-session memory was used"


def test_unrelated_task_gets_no_injection(engine, clock):
    run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted", FIX_SCRIPT)
    assert engine.prompt("claude-code", "s2", "Write documentation for the kubernetes deployment charts") is None


def test_follow_up_prompt_continues_and_refinalizes_same_execution(engine, clock):
    outcome, _ = run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted",
                          [step(EDIT), step(TEST, False, "E   AssertionError: still broken")])
    assert outcome.status == "failure"
    assert engine.prompt("claude-code", "s1", "still failing, try again") is None
    outcome2, _ = run_task(engine, clock, "s1", "ok", [step(EDIT), step(TEST)])
    assert outcome2.execution_id == outcome.execution_id and outcome2.status == "success"
    assert len(engine.store.list("Experience")) == 1


def test_verified_outcome_survives_later_inference(engine, clock):
    engine.prompt("claude-code", "s1", "Add pagination to the orders listing endpoint")
    engine.tool_start("claude-code", "s1", "t1", *EDIT)
    engine.tool_end("claude-code", "s1", "t1", *EDIT, True)
    engine.record_outcome("success", "manually verified in browser")
    outcome = engine.stop("claude-code", "s1")
    stored = engine.store.get("out-" + engine.store.latest("claude-code", "s1").id)
    assert stored.verified and stored.status == "success" and stored.evidence == "manually verified in browser"
    assert outcome is None or outcome.status == "success"


def test_failure_loop_triggers_one_replanning_alert(engine, clock):
    engine.prompt("claude-code", "s1", "Fix the flaky payment webhook signature verification")
    messages = []
    for i in range(6):
        clock.advance(20)
        cmd = ("Bash", {"command": f"python -m pytest tests/test_webhook.py -k sig{i}"})
        engine.tool_start("claude-code", "s1", f"t{i}", *cmd)
        messages.append(engine.tool_end("claude-code", "s1", f"t{i}", *cmd, False, "E   ValueError: bad signature"))
    alerts = [m for m in messages if m]
    assert len(alerts) == 1, "cooldown and once-per-kind prevent nagging"
    assert "consecutive tool failures" in alerts[0] and "Recommendation:" in alerts[0]


def test_exploration_does_not_trigger_stagnation(engine, clock):
    engine.prompt("claude-code", "s1", "Explain how the caching layer decides when to invalidate entries")
    messages = []
    for i in range(20):
        clock.advance(40)
        tool = ("Read", {"file_path": f"src/cache/part{i}.py"})
        engine.tool_start("claude-code", "s1", f"r{i}", *tool)
        messages.append(engine.tool_end("claude-code", "s1", f"r{i}", *tool, True, None, 2000))
    assert not any(messages)


def test_identical_failing_call_warns_before_third_attempt(engine, clock):
    engine.prompt("claude-code", "s1", "Get the database migration to apply cleanly again")
    cmd = ("Bash", {"command": "alembic upgrade head"})
    warnings = []
    for i in range(3):
        clock.advance(10)
        warnings.append(engine.tool_start("claude-code", "s1", f"t{i}", *cmd))
        engine.tool_end("claude-code", "s1", f"t{i}", *cmd, False, "sqlalchemy.exc.OperationalError: no such table")
    assert warnings[:2] == [None, None] and "already failed 2x" in warnings[2]


def test_tool_calls_without_prompt_are_captured_then_described_via_mcp(engine, clock):
    engine.tool_start("cursor", "c1", None, *READ)
    engine.tool_end("cursor", "c1", None, *READ, True, None, 4000)
    execution = engine.store.latest("cursor", "c1")
    assert engine.store.get(execution.task_id).description == UNTRACKED
    same, context = engine.context_for("Fix the login redirect loop after logout")
    assert same.id == execution.id and "Working approach:" in context.text
    assert engine.store.get(execution.task_id).task_class == "debug"


def test_duplicate_hook_delivery_is_idempotent(engine, clock):
    engine.prompt("claude-code", "s1", "Refactor the billing module into smaller services")
    for _ in range(2):
        engine.tool_start("claude-code", "s1", "t1", *EDIT)
        engine.tool_end("claude-code", "s1", "t1", *EDIT, True, None, 100)
    assert len(engine.store.list("ToolCall")) == 1
    assert engine.store.latest("claude-code", "s1").output_tokens_estimate == 25


def test_path_comparison_requires_outcome_and_comparable_evidence(engine, clock):
    unknown, _ = run_task(engine, clock, "s1", "Explore how the caching layer invalidates entries", [step(READ), step(GREP)])
    assert unknown.status == "unknown" and unknown.estimated_regret is None
    failed, _ = run_task(engine, clock, "s2", "Fix the cache invalidation bug for user profiles",
                         [step(EDIT), step(TEST, False, "E   AssertionError: stale profile")])
    assert failed.status == "failure"
    assert failed.estimated_regret is None
    assert failed.best_alternative is None
    assert "no proven better option" in failed.regret_basis


def test_choose_path_accepts_custom_strategy(engine, clock):
    engine.prompt("claude-code", "s1", "Migrate the settings loader from yaml to toml")
    path = engine.choose_path("spike-then-rewrite", ["Prototype toml loader", "Swap callers"])
    execution = engine.store.latest("claude-code", "s1")
    assert execution.chosen_path_id == path.id and not execution.chosen_inferred
    assert path.uncertainty == 1.0


def test_candidate_paths_reports_explicit_choice(engine, clock):
    engine.prompt("claude-code", "s1", "Migrate the settings loader from yaml to toml")
    chosen = engine.choose_path("spike-then-rewrite", ["Prototype toml loader", "Swap callers"])

    execution, task, paths = engine.candidate_paths()
    assert any(p.id == chosen.id for p in paths)
    text = engine.paths()
    assert "OPENREFLEX / PATHS" in text
    assert "Followed       spike-then-rewrite (explicit)" in text
    assert "[followed]" in text


def test_candidate_paths_reports_inferred_choice_after_finalize(engine, clock):
    outcome, _ = run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted", FIX_SCRIPT)
    execution = engine.store.get(outcome.execution_id)
    assert execution.chosen_inferred

    text = engine.paths()
    assert "inferred from tool calls" in text


def test_candidate_paths_reports_not_yet_determined_while_running(engine, clock):
    engine.prompt("claude-code", "s1", "Fix the login bug where expired tokens are accepted")

    text = engine.paths()
    assert "Followed       not yet determined (execution still running)" in text


def test_compound_commands_are_categorized_by_the_program_they_run():
    from openreflex.privacy import categorize
    assert categorize("Bash", {"command": "Get-Location; rg --files -g '*test*' -g pytest.ini"}) == "search"
    assert categorize("Bash", {"command": "rg pytest; python -m pytest tests -q"}) == "test"
    assert categorize("Bash", {"command": "cd web && npm run lint"}) == "lint"
    assert categorize("Bash", {"command": "Get-Content dates.py; Get-Content tests/test_dates.py"}) == "read"


def test_error_signature_prefers_the_failing_test_over_the_run_tally():
    from openreflex.privacy import error_signature
    output = ("E       assert (2024, 2, 15) == (2024, 3, 15)\n"
              "FAILED tests/test_dates.py::test_parse_date - assert (2024, 2, 15) == (2024, 3, 15)\n"
              "1 failed in {}\n")
    assert "test_parse_date" in error_signature(output.format("0.12s"))
    assert error_signature(output.format("0.12s")) == error_signature(output.format("1.08s"))
