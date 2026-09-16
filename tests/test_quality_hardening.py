import asyncio
import json
from pathlib import Path

from openreflex import hooks
from openreflex.engine import Engine
from openreflex.mcp_server import build_server
from openreflex.project import approve
from openreflex.store import Store


def _factory(database: Path, clock):
    def make(project: Path) -> Engine:
        return Engine(project, Store(database), clock=clock)
    return make


def _call(factory, agent, event, payload):
    return hooks.handle(agent, event, payload, engine_factory=factory)


def test_claude_round_trip_counts_tools_and_output_tokens(project, tmp_path, clock):
    """A real prompt -> tools -> stop lifecycle must never recap a worked task as zero calls/tokens."""
    approve(project)
    factory = _factory(tmp_path / "quality-hooks.sqlite3", clock)
    base = {"session_id": "quality", "cwd": str(project)}
    _call(factory, "claude-code", "UserPromptSubmit",
          {**base, "prompt": "Refactor the authentication cache and verify the behaviour with tests"})

    steps = [
        ("Read", {"file_path": str(project / "src" / "auth.py")}, "a" * 5000),
        ("Grep", {"pattern": "cache", "path": str(project / "src")}, "b" * 5000),
        ("Bash", {"command": "pytest -q"}, "3 passed in 0.12s\n" + "c" * 5000),
    ]
    for index, (name, arguments, output) in enumerate(steps):
        clock.advance(5)
        payload = {**base, "tool_name": name, "tool_input": arguments, "tool_use_id": f"t{index}"}
        _call(factory, "claude-code", "PreToolUse", payload)
        _call(factory, "claude-code", "PostToolUse", {**payload, "tool_response": {"stdout": output}})

    clock.advance(5)
    rendered = json.loads(_call(factory, "claude-code", "Stop", base))
    recap = rendered["systemMessage"]
    assert "3 calls" in recap
    assert "0.0k tokens" not in recap

    engine = factory(project)
    try:
        outcome = engine.store.list("Outcome", limit=1)[0]
        calls = engine.store.list("ToolCall", "execution_id", outcome.execution_id)
        assert len(calls) == 3
        assert outcome.tool_calls == 3
        assert outcome.output_tokens_estimate > 0
    finally:
        engine.close()


def test_unknown_completion_does_not_publish_predicted_regret(project, tmp_path, clock):
    """No verification means unknown outcome, so completion must not substitute a path estimate for measured regret."""
    approve(project)
    factory = _factory(tmp_path / "unknown-hooks.sqlite3", clock)
    base = {"session_id": "unknown", "cwd": str(project)}
    _call(factory, "claude-code", "UserPromptSubmit",
          {**base, "prompt": "Compare two possible designs for the cache invalidation mechanism"})
    clock.advance(30)
    rendered = json.loads(_call(factory, "claude-code", "Stop", base))
    recap = rendered["systemMessage"]
    assert "unknown" in recap
    assert "regret" not in recap


def test_machine_readable_tools_publish_real_output_schemas(project):
    """Machine-readable MCP tools must expose semantic fields, not only the primitive {'result': ...} wrapper."""
    approve(project)
    tools = {tool.name: tool for tool in asyncio.run(build_server(project).list_tools())}
    expected = {
        "get_reflex_score": {"available", "reflex_score", "signals", "policy_version"},
        "search_experience": {"experiences", "lessons"},
        "explain_node": {"root", "nodes", "edges"},
        "get_project_insights": {"engagement", "experience_reuse", "outcomes", "routing"},
    }
    for name, fields in expected.items():
        schema = tools[name].outputSchema
        assert schema and schema.get("type") == "object", name
        properties = set(schema.get("properties", {}))
        assert fields <= properties, (name, properties)
        assert properties != {"result"}, name

    search_schema = tools["search_experience"].inputSchema["properties"]
    assert search_schema["limit"]["minimum"] == 1
    assert search_schema["limit"]["maximum"] == 20
    evidence_schema = tools["record_outcome"].inputSchema["properties"]["evidence"]
    assert evidence_schema["maxLength"] == 500
