import json

from openreflex.execution_state import METRIC_SEMANTICS, STATE_SCHEMA_VERSION, build_execution_state
from openreflex.models import Execution, ToolCall
from openreflex.routing import Budget


def execution(**updates):
    values = {
        "id": "exec-1",
        "task_id": "task-1",
        "recommended_path_id": "path-1",
        "started_at": 100.0,
        "last_progress_at": 140.0,
        "context_tokens": 120,
        "output_tokens_estimate": 500,
        "compactions": 1,
    }
    values.update(updates)
    return Execution(**values)


def call(external_id, category, status="success", *, signature=None, files=None, started_at=110.0):
    return ToolCall(
        execution_id="exec-1",
        external_id=external_id,
        name="private-tool-name",
        category=category,
        fingerprint=f"fingerprint-{external_id}",
        files=files or [],
        started_at=started_at,
        ended_at=started_at + 1,
        status=status,
        error_signature=signature,
    )


def test_execution_state_is_reproducible_for_same_observation():
    run = execution()
    calls = [call("1", "read"), call("2", "edit"), call("3", "test")]
    budget = Budget(seconds=100, tool_calls=10, context_tokens=1000, source="estimated")

    first = build_execution_state(run, calls, budget, 150.0, active_seconds=50.0)
    second = build_execution_state(run, calls, budget, 150.0, active_seconds=50.0)

    assert first == second
    assert first.schema_version == STATE_SCHEMA_VERSION
    assert first.observation_fingerprint == second.observation_fingerprint


def test_execution_state_uses_existing_budget_semantics():
    run = execution(output_tokens_estimate=500)
    calls = [call("1", "read"), call("2", "test")]
    budget = Budget(seconds=100, tool_calls=10, context_tokens=1000, source="limit")

    state = build_execution_state(run, calls, budget, 150.0, active_seconds=50.0)

    assert state.time_budget_ratio == 0.5
    assert state.tool_budget_ratio == 0.2
    assert state.token_budget_ratio == 0.5
    assert state.budget_pressure == 0.5
    assert state.budget_source == "limit"


def test_execution_state_records_progress_without_content():
    run = execution()
    calls = [
        call("1", "edit", files=["src/auth/secrets.py"]),
        call("2", "test", "failure", signature="AssertionError: bearer secret-token exposed"),
        call("3", "test", "failure", signature="AssertionError: bearer secret-token exposed"),
    ]
    budget = Budget(seconds=100, tool_calls=10, context_tokens=1000, source="estimated")

    state = build_execution_state(run, calls, budget, 150.0, active_seconds=50.0)
    encoded = json.dumps(state.as_dict(), sort_keys=True)

    assert state.successful_edits == 1
    assert state.verification_failures == 2
    assert state.unique_files_touched == 1
    assert state.distinct_failure_signatures == 1
    assert state.max_failure_repeat == 2
    assert "src/auth" not in encoded
    assert "secret-token" not in encoded
    assert "private-tool-name" not in encoded


def test_fingerprint_represents_observation_not_execution_identity():
    budget = Budget(seconds=100, tool_calls=10, context_tokens=1000, source="estimated")
    calls = [call("1", "read"), call("2", "test")]

    first = build_execution_state(execution(id="exec-a", task_id="task-a"), calls, budget, 150.0, active_seconds=50.0)
    second = build_execution_state(execution(id="exec-b", task_id="task-b"), calls, budget, 150.0, active_seconds=50.0)

    assert first.observation_fingerprint == second.observation_fingerprint
    assert first.execution_id != second.execution_id


def test_metric_contract_documents_learning_features():
    required = {
        "active_seconds",
        "seconds_since_progress",
        "tool_calls_total",
        "tool_calls_completed",
        "tool_calls_failed",
        "output_tokens_estimate",
        "context_tokens",
        "budget_pressure",
        "verification_successes",
        "verification_failures",
        "successful_edits",
        "unique_files_touched",
        "distinct_failure_signatures",
        "max_failure_repeat",
    }
    assert required <= METRIC_SEMANTICS.keys()
    assert all(METRIC_SEMANTICS[name].strip() for name in required)
