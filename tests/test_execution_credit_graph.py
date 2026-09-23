import json
from openreflex.models import Experience, Outcome, ProjectReflex, ToolCall
from openreflex.reflexes import compile_for_experience, execution_credit_graph
from openreflex.routing import embed
from openreflex.store import Store


def _record(store, index, categories, *, verified=True, status="success", repeated=None):
    execution_id = f"credit-exec-{index}"
    outcome = Outcome(
        id=f"credit-out-{index}",
        execution_id=execution_id,
        status=status,
        evidence="verification observed" if verified else "inferred",
        verified=verified,
        elapsed_seconds=30,
        tool_calls=len(categories),
        failures=0 if status == "success" else 1,
        output_tokens_estimate=100,
        chosen_strategy="inspect-first",
    )
    experience = Experience(
        id=f"credit-exp-{index}",
        task_id=f"credit-task-{index}",
        execution_id=execution_id,
        outcome_id=outcome.id,
        agent="claude-code",
        description="Update Helm values for the worker deployment",
        task_class="build",
        strategy="inspect-first",
        status=status,
        elapsed_seconds=30,
        tool_calls=len(categories),
        output_tokens_estimate=100,
        files=["charts/app/values.yaml"],
        embedding=embed("Update Helm values for the worker deployment"),
        created_at=float(index),
        task_mode="build",
    )
    store.put(outcome)
    store.put(experience)

    repeated = repeated or {}
    offset = 0
    for category in categories:
        for repeat in range(int(repeated.get(category, 1))):
            call = ToolCall(
                id=f"credit-call-{index}-{category}-{repeat}",
                execution_id=execution_id,
                external_id=f"ext-{index}-{category}-{repeat}",
                name="Bash" if category in {"lint", "test", "build", "vcs"} else category.title(),
                category=category,
                fingerprint=f"fp-{index}-{category}-{repeat}",
                files=["charts/app/values.yaml"] if category in {"read", "edit"} else [],
                started_at=float(index * 100 + offset),
                ended_at=float(index * 100 + offset + 1),
                status="success",
            )
            store.put(call)
            offset += 2
    return experience


def _by_action(graph):
    return {item["action"]: item for item in graph}


def test_sparse_history_never_compresses_from_one_lucky_run(tmp_path):
    store = Store(tmp_path / "credit.sqlite3")
    try:
        experience = _record(store, 1, ["read", "edit", "lint"], verified=True)
        graph = execution_credit_graph(store, [experience])

        assert graph
        assert all(item["known"] == 1 for item in graph)
        assert all(item["spine"] is False for item in graph)
    finally:
        store.close()


def test_success_when_action_is_absent_reduces_credit_and_compresses_incidental_step(tmp_path):
    store = Store(tmp_path / "absence.sqlite3")
    try:
        experiences = [
            _record(store, 1, ["read", "edit", "lint"]),
            _record(store, 2, ["read", "edit", "lint"]),
            _record(store, 3, ["edit", "lint"]),
            _record(store, 4, ["edit", "lint"]),
        ]

        graph = _by_action(execution_credit_graph(store, experiences))
        assert graph["read"]["success_rate_with"] < 1.0
        assert graph["read"]["success_rate_without"] < 1.0
        assert graph["read"]["association"] == 0.0
        assert graph["read"]["evidence"] == "comparative"
        assert graph["read"]["spine"] is False
        assert graph["edit"]["spine"] is True
        assert graph["lint"]["spine"] is True
        assert graph["edit"]["credit"] > graph["read"]["credit"]

        reflex = compile_for_experience(store, experiences[-1], now=100)
        assert reflex.family == "helm-values"
        assert reflex.credit_graph
        assert reflex.credit_version == 2
        assert reflex.procedure == [
            "Update charts/app/values.yaml",
            "Run the project validation checks",
        ]
    finally:
        store.close()


def test_repeated_calls_are_recorded_as_redundancy_not_extra_support(tmp_path):
    store = Store(tmp_path / "redundancy.sqlite3")
    try:
        experiences = [
            _record(store, 1, ["read", "edit", "lint"], repeated={"read": 3}),
            _record(store, 2, ["read", "edit", "lint"], repeated={"read": 2}),
            _record(store, 3, ["read", "edit", "lint"]),
            _record(store, 4, ["read", "edit", "lint"]),
        ]
        graph = _by_action(execution_credit_graph(store, experiences))

        assert graph["read"]["support"] == 4
        assert graph["read"]["redundancy"] > 0
        assert graph["read"]["spine"] is False
        assert graph["read"]["credit"] < graph["edit"]["credit"]
    finally:
        store.close()


def test_credit_graph_round_trips_with_project_reflex(tmp_path):
    store = Store(tmp_path / "roundtrip.sqlite3")
    try:
        experiences = [
            _record(store, 1, ["read", "edit", "lint"]),
            _record(store, 2, ["read", "edit", "lint"]),
            _record(store, 3, ["edit", "lint"]),
            _record(store, 4, ["edit", "lint"]),
        ]
        reflex = compile_for_experience(store, experiences[-1], now=100)
        restored = store.get_reflex(reflex.id)

        assert restored.credit_graph == reflex.credit_graph
        assert any(item["spine"] for item in restored.credit_graph)
    finally:
        store.close()


def test_pre_credit_reflex_json_loads_with_empty_graph(tmp_path):
    store = Store(tmp_path / "legacy.sqlite3")
    try:
        legacy = ProjectReflex(
            id="legacy-reflex",
            name="Legacy procedure",
            family="tests",
            task_mode="build",
            task_class="test",
            state="learned",
            procedure=["Run the project tests"],
            support_count=2,
            success_count=2,
            verified_count=0,
            confidence=0.6,
        )
        payload = legacy.model_dump()
        payload.pop("credit_graph", None)
        restored = ProjectReflex.model_validate_json(json.dumps(payload))

        assert restored.credit_graph == []
        assert restored.credit_version == 0
    finally:
        store.close()


def test_presence_only_actions_cannot_enter_credit_spine(tmp_path):
    store = Store(tmp_path / "presence-only.sqlite3")
    try:
        experiences = [
            _record(store, 1, ["read", "edit", "lint"]),
            _record(store, 2, ["read", "edit", "lint"]),
            _record(store, 3, ["read", "edit", "lint"]),
            _record(store, 4, ["read", "edit", "lint"]),
        ]
        graph = _by_action(execution_credit_graph(store, experiences))

        assert graph["edit"]["evidence"] == "presence-only"
        assert graph["edit"]["association"] is None
        assert graph["edit"]["confidence"] <= 0.45
        assert graph["edit"]["spine"] is False
    finally:
        store.close()


def test_failures_without_actions_create_comparative_credit_spine(tmp_path):
    store = Store(tmp_path / "comparative.sqlite3")
    try:
        experiences = [
            _record(store, 1, ["search", "read", "edit", "test"], verified=True),
            _record(store, 2, ["search", "read", "edit", "test"], verified=True),
            _record(store, 3, ["search", "read", "edit", "test"], verified=True),
            _record(store, 4, ["search", "read", "edit", "test"], verified=True),
            _record(store, 5, ["search", "read"], verified=False, status="failure"),
            _record(store, 6, ["search", "read"], verified=False, status="failure"),
        ]
        graph = _by_action(execution_credit_graph(store, experiences))

        assert graph["edit"]["spine"] is True
        assert graph["test"]["spine"] is True
        assert graph["edit"]["association"] > 0
        assert graph["edit"]["confidence"] >= 0.5
        assert graph["search"]["spine"] is False
        assert graph["read"]["spine"] is False
        assert graph["search"]["evidence"] == "presence-only"
    finally:
        store.close()
