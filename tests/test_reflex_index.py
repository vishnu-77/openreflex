from openreflex.engine import Engine
from openreflex.project_memory import build_snapshot, load_snapshot
from openreflex.reflex_index import account_project_context, context_for_task, reinforce_latest_execution

from .conftest import run_task
from .test_engine import FIX_SCRIPT


def test_verified_execution_reinforces_project_file_without_rewriting_structural_provenance(project, clock):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "auth.py").write_text("def check(): pass\n", encoding="utf-8")
    build_snapshot(project)

    engine = Engine(project, clock=clock)
    try:
        outcome, _ = run_task(engine, clock, "s1", "Fix the login bug where expired tokens are accepted", FIX_SCRIPT)
        engine.record_outcome("success", "pytest passed", execution_id=outcome.execution_id)
    finally:
        engine.close()

    counts = reinforce_latest_execution(project, "claude-code", "s1")
    snapshot = load_snapshot(project)
    auth = next(item for item in snapshot["indexed_files"] if item["path"] == "src/auth.py")

    assert auth["role"] == "execution-observed"
    assert auth["evidence_state"] == "verified"
    assert auth["verified_successes"] == 1
    assert counts["experiences"] == 1 and counts["verified"] == 1

    context = context_for_task(project, "Fix expired token handling in auth")
    assert "src/auth.py" in context
    assert "explicit verified-success observation" in context
    assert "structural prior" in context


def test_repeated_verified_success_promotes_file_to_reinforced(project, clock):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "auth.py").write_text("def check(): pass\n", encoding="utf-8")
    build_snapshot(project)

    engine = Engine(project, clock=clock)
    try:
        for index in range(2):
            outcome, _ = run_task(
                engine, clock, f"s{index}",
                f"Fix the login bug where expired tokens are accepted variant {index}", FIX_SCRIPT,
            )
            engine.record_outcome("success", "pytest passed", execution_id=outcome.execution_id)
            reinforce_latest_execution(project, "claude-code", f"s{index}")
            clock.advance(60)
    finally:
        engine.close()

    auth = next(item for item in load_snapshot(project)["indexed_files"] if item["path"] == "src/auth.py")
    assert auth["evidence_state"] == "reinforced"
    assert auth["verified_successes"] == 2


def test_project_context_tokens_are_counted_once_per_execution(project, clock):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    engine = Engine(project, clock=clock)
    try:
        engine.prompt("claude-code", "s", "Fix the authentication flow where expired tokens are accepted")
        execution = engine.current_execution("claude-code", "s")
        before = execution.context_tokens or 0
    finally:
        engine.close()

    context = "Project memory: Python.\nEvidence: repository structure/config only."
    account_project_context(project, "claude-code", "s", context)
    account_project_context(project, "claude-code", "s", context)

    check = Engine(project, clock=clock)
    try:
        execution = check.current_execution("claude-code", "s")
        expected = round(len(context) / check.policy.number("context.chars_per_token"))
        assert execution.context_tokens == before + expected
    finally:
        check.close()
