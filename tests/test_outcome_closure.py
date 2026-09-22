import json
from pathlib import Path

from openreflex import hooks, metrics
from openreflex.engine import Engine
from openreflex.mcp_contracts import ExperienceReuseMetrics
from openreflex.privacy import categorize
from openreflex.project import approve, approval
from openreflex.store import Store

from .conftest import run_task
from .test_engine import FIX_SCRIPT


def _factory(tmp_path, clock):
    database = tmp_path / "closure.sqlite3"

    def make(project: Path) -> Engine:
        return Engine(project, Store(database), clock=clock)

    return make


def _call(factory, project, event, payload):
    return hooks.handle("claude-code", event, {"session_id": "s", "cwd": str(project), **payload}, engine_factory=factory)


def _successful_tool(factory, project, tool, arguments, tool_id):
    payload = {"tool_name": tool, "tool_input": arguments, "tool_use_id": tool_id}
    _call(factory, project, "PreToolUse", payload)
    _call(factory, project, "PostToolUse", {**payload, "tool_response": {"stdout": "ok"}})


def test_first_stop_after_unverified_edit_is_silent(tmp_path, project, clock):
    approve(project)
    factory = _factory(tmp_path, clock)
    _call(factory, project, "UserPromptSubmit", {"prompt": "Fix the Helm values bug causing invalid deployment configuration"})
    _successful_tool(factory, project, "Edit", {"file_path": "charts/app/values.yaml"}, "e1")

    first = _call(factory, project, "Stop", {})
    assert first == ""

    engine = factory(project)
    try:
        execution = engine.store.latest("claude-code", "s")
        outcome = engine.store.find("Outcome", execution_id=execution.id)[0]
        assert outcome.status == "unknown"
        assert outcome.evidence == "no verification observed after the last edit"
    finally:
        engine.close()

    assert _call(factory, project, "Stop", {"stop_hook_active": True}) == ""


def test_read_only_exploration_can_finish_unknown_without_continuation(tmp_path, project, clock):
    approve(project)
    factory = _factory(tmp_path, clock)
    _call(factory, project, "UserPromptSubmit", {"prompt": "Investigate how the Helm release values are assembled today"})
    _successful_tool(factory, project, "Read", {"file_path": "charts/app/values.yaml"}, "r1")

    output = _call(factory, project, "Stop", {})
    if output:
        data = json.loads(output)
        assert "additionalContext" not in data.get("hookSpecificOutput", {})


def test_verified_helm_edit_finishes_without_closure_continuation(tmp_path, project, clock):
    approve(project)
    factory = _factory(tmp_path, clock)
    _call(factory, project, "UserPromptSubmit", {"prompt": "Fix the Helm chart validation failure caused by missing defaults"})
    _successful_tool(factory, project, "Edit", {"file_path": "charts/app/values.yaml"}, "e1")
    clock.advance(1)
    _successful_tool(factory, project, "Bash", {"command": "helm lint charts/app"}, "t1")

    output = _call(factory, project, "Stop", {})
    if output:
        data = json.loads(output)
        assert "additionalContext" not in data.get("hookSpecificOutput", {})


def test_helm_verification_commands_are_classified_as_verification():
    cases = {
        "helm lint charts/app": "lint",
        "helm template app charts/app -f values.yaml": "build",
        "helm unittest charts/app": "test",
        "helm test app": "test",
        "ct lint --charts charts/app": "lint",
        "ct install --charts charts/app": "test",
        "kubeconform -strict rendered.yaml": "lint",
        "helm upgrade app charts/app --dry-run --install": "build",
    }
    for command, expected in cases.items():
        assert categorize("Bash", {"command": command}) == expected, command


def test_reuse_rate_is_coverage_not_a_claim_of_benefit(engine, clock, project):
    approve(project)
    for index in range(3):
        run_task(engine, clock, f"reuse-{index}",
                 f"Fix the login bug where expired tokens are accepted variant {index}", FIX_SCRIPT)
        clock.advance(3600)

    data = metrics.project_metrics(engine, approval(project), now=clock.now)
    reuse = data["experience_reuse"]
    assert reuse["reuse_rate"] == round(2 / 3, 3)
    assert reuse["benefit_rate"] == reuse["reuse_rate"], "legacy alias must remain compatible"
    assert "coverage, not benefit" in ExperienceReuseMetrics.model_fields["reuse_rate"].description
    assert "does not measure causal benefit" in ExperienceReuseMetrics.model_fields["benefit_rate"].description
