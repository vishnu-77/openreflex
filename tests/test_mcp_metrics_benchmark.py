import asyncio
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from openreflex import benchmark, metrics
from openreflex.engine import Engine
from openreflex.mcp_server import build_server
from openreflex.project import approve, approval

from .conftest import run_task
from .test_engine import FIX_SCRIPT


def tool_text(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return "".join(getattr(item, "text", "") for item in content)


def test_mcp_tools_require_approval_then_work(project, clock):
    server = build_server(project)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"get_execution_context", "choose_path", "check_progress", "record_outcome", "search_experience",
            "explain_decision", "get_execution_trace", "get_candidate_paths", "get_reflex_score", "explain_node",
            "get_project_insights", "approve_project", "forget_experience"} == names
    assert "not enabled" in tool_text(server, "get_execution_context", {"task": "Fix the login redirect loop"})
    assert "Not approved" in tool_text(server, "approve_project", {})
    assert "enabled" in tool_text(server, "approve_project", {"confirm": True})

    context = tool_text(server, "get_execution_context", {"task": "Fix the login redirect loop after logout"})
    assert "Suggested path" in context and "Candidate paths" in context and "Pareto-efficient" in context
    assert "OPENREFLEX / WHY" in tool_text(server, "explain_decision", {})
    assert "OPENREFLEX / TRACE" in tool_text(server, "get_execution_trace", {})
    assert "OPENREFLEX / PATHS" in tool_text(server, "get_candidate_paths", {})
    score = json.loads(tool_text(server, "get_reflex_score", {}))
    assert score["available"] is True and 0 <= score["reflex_score"] <= 100
    assert "Recorded chosen path: incremental" in tool_text(server, "choose_path", {"strategy": "incremental"})
    outcome = tool_text(server, "record_outcome", {"status": "success", "evidence": "pytest passed"})
    assert outcome.startswith("Outcome recorded: success")
    insights = json.loads(tool_text(server, "get_project_insights", {}))
    assert insights["outcomes"]["verified"] == 1
    # A task with real tool activity becomes an experience that can be searched for and forgotten.
    engine = Engine(project, clock=clock)
    try:
        run_task(engine, clock, "s-forget", "Fix the expired token bug in the session check", FIX_SCRIPT)
    finally:
        engine.close()
    found = json.loads(tool_text(server, "search_experience", {"query": "Fix the expired token bug in the session check"}))
    experience_id = found["experiences"][0]["id"]
    assert "Not forgotten" in tool_text(server, "forget_experience", {"experience_id": experience_id})
    assert "Unknown experience id" in tool_text(server, "forget_experience", {"experience_id": "exp-nope", "confirm": True})
    forgotten = tool_text(server, "forget_experience", {"experience_id": experience_id, "confirm": True})
    assert forgotten.startswith("Forgotten:") and "1 Task" in forgotten and "1 Experience" in forgotten
    remaining = json.loads(tool_text(server, "search_experience", {"query": "Fix the expired token bug in the session check"}))["experiences"]
    assert all(item["id"] != experience_id for item in remaining)
    with pytest.raises(ToolError, match="Unknown graph node"):
        tool_text(server, "explain_node", {"node_id": experience_id})
    assert json.loads(tool_text(server, "get_project_insights", {}))["engagement"]["tasks"] == 1


def test_metrics_report_reuse_and_path_checks(engine, clock, project):
    record = approve(project)
    for i in range(3):
        run_task(engine, clock, f"s{i}", f"Fix the login bug where expired tokens are accepted variant {i}", FIX_SCRIPT)
        clock.advance(3600)
    data = metrics.project_metrics(engine, approval(project), now=clock.now)
    assert data["engagement"]["experiences"] == 3
    assert data["experience_reuse"]["benefit_rate"] == round(2 / 3, 3)
    assert data["efficiency_observational"]["with_prior_experience"]["n"] == 2
    assert data["routing"]["retrospective_best"] == {"debug": "test-first"}
    assert record["approved_at"] > 0


def test_benchmark_guided_arm_learns_in_simulation():
    report = benchmark.run_benchmark(episodes=60, seeds=1)
    guided, baseline = report["guided"], report["baseline"]
    assert report["kind"] == "simulation" and report["assumptions"]
    assert guided["tool_calls"] < baseline["tool_calls"]
    assert guided["success_rate"] >= baseline["success_rate"] - 0.05
    assert guided["regret_last_quarter"] < guided["regret_first_quarter"]
    assert "not evidence of real-world gains" in benchmark.format_report(report)


def test_every_mcp_tool_is_fully_described(project):
    tools = asyncio.run(build_server(project).list_tools())
    for tool in tools:
        assert tool.title and len(tool.description) > 200, tool.name
        for label in ("Returns:", "Use when:", "Side effects:", "Errors:"):
            assert label in tool.description, f"{tool.name} lacks {label}"
        assert tool.annotations is not None and tool.annotations.openWorldHint is False, tool.name
        for name, schema in tool.inputSchema.get("properties", {}).items():
            assert schema.get("description"), f"{tool.name}.{name} has no description"
    read_only = {t.name for t in tools if t.annotations.readOnlyHint}
    assert read_only == {"check_progress", "explain_decision", "get_execution_trace", "get_candidate_paths",
                         "get_reflex_score", "search_experience", "explain_node", "get_project_insights"}
