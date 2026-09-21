import sqlite3

from openreflex.models import Experience, Outcome, ProjectReflex, ToolCall
from openreflex.reflexes import compile_for_experience, match_reflex
from openreflex.routing import embed
from openreflex.store import SCHEMA_VERSION, Store

from .conftest import run_task


def test_project_reflex_round_trip_and_schema_migration(tmp_path):
    store = Store(tmp_path / "memory.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 3
        reflex = ProjectReflex(
            id="reflex-helm-values",
            name="Helm values change",
            task_mode="build",
            task_class="debug",
            state="learned",
            seed_strategy="inspect-first",
            procedure=["Inspect values.yaml", "Make the focused change", "Verify the rendered chart"],
            evidence_ids=["exp-1", "exp-2"],
            support_count=2,
            success_count=2,
            verified_count=1,
            confidence=0.72,
            embedding=[1.0, 0.0],
            file_patterns=["values.yaml"],
            created_at=1.0,
            updated_at=2.0,
        )
        store.put_reflex(reflex)

        restored = store.get_reflex(reflex.id)
        assert restored.name == "Helm values change"
        assert restored.procedure == reflex.procedure
        assert store.list_reflexes(task_mode="build", states=("learned",)) == [restored]
    finally:
        store.close()


def test_existing_v2_database_gets_reflex_table_without_rewriting_nodes(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = Store(path)
    store.set_meta("sentinel", "kept")
    store.close()

    # Simulate an existing 0.5.x database that has not yet run the v3 migration.
    db = sqlite3.connect(path)
    db.execute("DROP TABLE project_reflexes")
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()

    upgraded = Store(path)
    try:
        assert upgraded.get_meta("sentinel") == "kept"
        assert upgraded.db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert upgraded.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_reflexes'"
        ).fetchone() is not None
    finally:
        upgraded.close()


def _experience(index: int, *, verified: bool = True) -> tuple[Experience, Outcome, list[ToolCall]]:
    execution = f"exec-{index}"
    outcome = Outcome(
        id=f"out-{index}",
        execution_id=execution,
        status="success",
        evidence="helm lint passed",
        verified=verified,
        elapsed_seconds=90,
        tool_calls=3,
        failures=0,
        output_tokens_estimate=500,
        chosen_strategy="inspect-first",
    )
    experience = Experience(
        id=f"exp-{index}",
        task_id=f"task-{index}",
        execution_id=execution,
        outcome_id=outcome.id,
        agent="claude-code",
        description="Update Helm values for the worker deployment",
        task_class="build",
        strategy="inspect-first",
        status="success",
        elapsed_seconds=90,
        tool_calls=3,
        output_tokens_estimate=500,
        files=["charts/app/values.yaml"],
        embedding=embed("Update Helm values for the worker deployment"),
        created_at=float(index),
        task_mode="build",
    )
    calls = [
        ToolCall(id=f"read-{index}", execution_id=execution, external_id=f"r-{index}", name="Read",
                 category="read", fingerprint=f"r{index}", files=["charts/app/values.yaml"],
                 started_at=float(index), ended_at=float(index) + 1, status="success"),
        ToolCall(id=f"edit-{index}", execution_id=execution, external_id=f"e-{index}", name="Edit",
                 category="edit", fingerprint=f"e{index}", files=["charts/app/values.yaml"],
                 started_at=float(index) + 2, ended_at=float(index) + 3, status="success"),
        ToolCall(id=f"lint-{index}", execution_id=execution, external_id=f"l-{index}", name="Bash",
                 category="lint", fingerprint=f"l{index}", files=[],
                 started_at=float(index) + 4, ended_at=float(index) + 5, status="success"),
    ]
    return experience, outcome, calls


def test_compiler_promotes_repeated_project_procedure(tmp_path):
    store = Store(tmp_path / "compiler.sqlite3")
    try:
        latest = None
        for index in range(1, 5):
            experience, outcome, calls = _experience(index)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            latest = compile_for_experience(store, experience, now=100 + index)

        assert latest is not None
        assert latest.name == "Helm values change"
        assert latest.state == "proven"
        assert latest.success_count == 4
        assert latest.verified_count == 4
        assert latest.seed_strategy == "inspect-first"
        assert latest.file_patterns == ["charts/app/values.yaml"]
        assert latest.procedure == [
            "Inspect charts/app/values.yaml",
            "Update charts/app/values.yaml",
            "Run the project validation checks",
        ]
    finally:
        store.close()


def test_compiler_does_not_surface_single_run_candidate(tmp_path):
    store = Store(tmp_path / "candidate.sqlite3")
    try:
        experience, outcome, calls = _experience(1)
        store.put(outcome)
        store.put(experience)
        for call in calls:
            store.put(call)
        candidate = compile_for_experience(store, experience, now=10)

        assert candidate.state == "candidate"
        assert match_reflex(store, experience.description, "build", "build") is None
    finally:
        store.close()


def test_matching_reflex_is_project_specific_and_similarity_gated(tmp_path):
    store = Store(tmp_path / "matching.sqlite3")
    try:
        for index in range(1, 3):
            experience, outcome, calls = _experience(index)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            compile_for_experience(store, experience, now=20 + index)

        matched = match_reflex(store, "Change the Helm values for worker resources", "build", "build")
        assert matched is not None
        reflex, score = matched
        assert reflex.name == "Helm values change"
        assert reflex.state == "learned"
        assert score >= 0.20

        assert match_reflex(store, "Rewrite the authentication token parser", "build", "debug") is None
    finally:
        store.close()


def test_engine_learns_then_reuses_project_reflex(engine, clock):
    script = [
        ("Read", {"file_path": "charts/app/values.yaml"}, True, None),
        ("Edit", {"file_path": "charts/app/values.yaml"}, True, None),
        ("Bash", {"command": "helm lint charts/app"}, True, None),
    ]
    for index in range(2):
        outcome, _ = run_task(
            engine, clock, f"helm-{index}",
            f"Update Helm values for the worker deployment variant {index}",
            script,
        )
        assert outcome.status == "success"
        clock.advance(20)

    learned = engine.store.list_reflexes(states=("learned", "proven"))
    assert len(learned) == 1
    assert learned[0].name == "Helm values change"

    execution, context = engine.context_for(
        "Update Helm values for the worker deployment resources",
        session="helm-next",
    )
    assert execution.reflex_id == learned[0].id
    assert context.reflex_id == learned[0].id
    assert "Reflex: Helm values change" in context.text
    assert "Procedure:" in context.text
    assert "inspect-first" not in context.text
    assert "test-first" not in context.text

    recap = engine.take_notice("mcp", "helm-next")
    assert recap is not None
    assert "Helm values change" in recap
    assert "inspect-first" not in recap
