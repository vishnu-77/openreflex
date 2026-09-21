import sqlite3

from openreflex.models import Experience, Outcome, ProjectReflex, ToolCall
from openreflex.reflexes import compile_for_experience, families_for_experience, match_reflex
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
            family="helm-values",
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
            module_patterns=["charts/app"],
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
        assert latest.module_patterns == ["charts/app"]
        assert latest.family == "helm-values"
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
    assert len(context.text) <= 900
    assert execution.context_tokens <= 225

    recap = engine.take_notice("mcp", "helm-next")
    assert recap is not None
    assert "Helm values change" in recap
    assert "inspect-first" not in recap


def test_contradictory_failures_make_a_learned_reflex_stale(tmp_path):
    store = Store(tmp_path / "stale.sqlite3")
    try:
        latest = None
        for index in range(1, 3):
            experience, outcome, calls = _experience(index)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            latest = compile_for_experience(store, experience, now=30 + index)
        assert latest is not None and latest.state == "learned"

        for index in range(3, 5):
            experience, outcome, calls = _experience(index)
            experience = experience.model_copy(update={"status": "failure"})
            outcome = outcome.model_copy(update={"status": "failure", "evidence": "verification failed"})
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            latest = compile_for_experience(store, experience, now=30 + index)

        assert latest is not None
        assert latest.state == "stale"
        assert latest.success_count == 2
        assert latest.support_count == 4
        assert match_reflex(store, "Update Helm values for worker resources", "build", "build") is None
    finally:
        store.close()



def _domain_experience(index: int, description: str, task_class: str, file_path: str):
    execution = f"domain-exec-{index}"
    outcome = Outcome(
        id=f"domain-out-{index}", execution_id=execution, status="success", evidence="verified",
        verified=True, elapsed_seconds=30, tool_calls=2, failures=0, output_tokens_estimate=100,
        chosen_strategy="inspect-first",
    )
    experience = Experience(
        id=f"domain-exp-{index}", task_id=f"domain-task-{index}", execution_id=execution,
        outcome_id=outcome.id, agent="claude-code", description=description, task_class=task_class,
        strategy="inspect-first", status="success", elapsed_seconds=30, tool_calls=2,
        output_tokens_estimate=100, files=[file_path], embedding=embed(description),
        created_at=float(index), task_mode="build",
    )
    return experience, outcome, [
        ToolCall(id=f"domain-read-{index}", execution_id=execution, external_id=f"dr-{index}",
                 name="Read", category="read", fingerprint=f"dr{index}", files=[file_path],
                 started_at=float(index), ended_at=float(index) + 1, status="success"),
        ToolCall(id=f"domain-edit-{index}", execution_id=execution, external_id=f"de-{index}",
                 name="Edit", category="edit", fingerprint=f"de{index}", files=[file_path],
                 started_at=float(index) + 2, ended_at=float(index) + 3, status="success"),
    ]


def test_project_family_accumulates_evidence_across_different_task_classes(tmp_path):
    store = Store(tmp_path / "cross-class.sqlite3")
    try:
        cases = [
            ("Fix login token validation", "debug", "src/auth/token.py"),
            ("Add OAuth callback support", "build", "src/auth/oauth.py"),
        ]
        latest = None
        for index, (description, task_class, file_path) in enumerate(cases, start=1):
            experience, outcome, calls = _domain_experience(index, description, task_class, file_path)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            latest = compile_for_experience(store, experience, now=100 + index)

        assert latest is not None
        assert latest.family == "authentication"
        assert latest.state == "learned"
        assert latest.support_count == 2
        assert "src/auth" in latest.module_patterns
        assert len(store.list_reflexes(states=("learned", "proven"))) == 1
    finally:
        store.close()


def test_novel_task_reuses_project_family_without_repeating_a_previous_task(tmp_path):
    store = Store(tmp_path / "novel-task.sqlite3")
    try:
        cases = [
            ("Fix login token validation", "debug", "src/auth/token.py"),
            ("Add OAuth callback support", "build", "src/auth/oauth.py"),
        ]
        for index, (description, task_class, file_path) in enumerate(cases, start=1):
            experience, outcome, calls = _domain_experience(index, description, task_class, file_path)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            compile_for_experience(store, experience, now=200 + index)

        matched = match_reflex(store, "Rotate sessions after privilege escalation", "build", "refactor")
        assert matched is not None
        reflex, score = matched
        assert reflex.family == "authentication"
        assert reflex.name == "Authentication change"
        assert score >= 0.28
    finally:
        store.close()


def test_module_locality_can_resolve_a_new_task_when_wording_differs(tmp_path):
    store = Store(tmp_path / "module-locality.sqlite3")
    try:
        cases = [
            ("Correct decimal rounding", "build", "src/payments/card.py"),
            ("Handle negative settlement values", "build", "src/payments/refund.py"),
        ]
        for index, (description, task_class, file_path) in enumerate(cases, start=1):
            experience, outcome, calls = _domain_experience(index, description, task_class, file_path)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            compile_for_experience(store, experience, now=300 + index)

        matched = match_reflex(store, "Change src/payments/settlement.py precision handling", "build", "build")
        assert matched is not None
        reflex, _ = matched
        assert "src/payments" in reflex.module_patterns
    finally:
        store.close()



def _runner_experience(index: int, description: str, files: list[str], *, task_mode: str = "build",
                       task_class: str = "build"):
    execution = f"runner-exec-{index}"
    outcome = Outcome(
        id=f"runner-out-{index}", execution_id=execution, status="success", evidence="verified",
        verified=True, elapsed_seconds=45, tool_calls=2, failures=0, output_tokens_estimate=120,
        chosen_strategy="inspect-first" if task_mode == "build" else "reason-first",
    )
    experience = Experience(
        id=f"runner-exp-{index}", task_id=f"runner-task-{index}", execution_id=execution,
        outcome_id=outcome.id, agent="claude-code", description=description, task_class=task_class,
        strategy=outcome.chosen_strategy, status="success", elapsed_seconds=45, tool_calls=2,
        output_tokens_estimate=120, files=files, embedding=embed(description), created_at=float(index),
        task_mode=task_mode,
    )
    calls = [
        ToolCall(id=f"runner-read-{index}", execution_id=execution, external_id=f"rr-{index}",
                 name="Read", category="read", fingerprint=f"rr{index}", files=files[:1],
                 started_at=float(index), ended_at=float(index) + 1, status="success"),
        ToolCall(id=f"runner-edit-{index}", execution_id=execution, external_id=f"re-{index}",
                 name="Edit", category="edit", fingerprint=f"re{index}", files=files[-1:],
                 started_at=float(index) + 2, ended_at=float(index) + 3, status="success"),
    ]
    return experience, outcome, calls


def test_one_execution_reinforces_terraform_helm_and_project_area_scopes(tmp_path):
    store = Store(tmp_path / "runner-scopes.sqlite3")
    try:
        experience, outcome, calls = _runner_experience(
            1,
            "Add GCP-native Bitbucket Kubernetes runner for quest-dev",
            [
                "terraform/config/runner.tf",
                "terraform/config/variables.tf",
                "helm/bitbucket-runner/Chart.yaml",
                "helm/bitbucket-runner/templates/deployment.yaml",
            ],
        )
        store.put(outcome)
        store.put(experience)
        for call in calls:
            store.put(call)

        compile_for_experience(store, experience, now=100)
        families = {reflex.family for reflex in store.list_reflexes(limit=100)}

        assert {"terraform", "helm-chart", "helm-template", "area:bitbucket-runner"} <= families
        assert "area:bitbucket-runner" in families_for_experience(experience)
    finally:
        store.close()


def test_runner_implementation_and_plan_promote_shared_project_area_across_modes(tmp_path):
    store = Store(tmp_path / "runner-area.sqlite3")
    try:
        implementation, outcome1, calls1 = _runner_experience(
            1,
            "Add GCP-native Bitbucket Kubernetes runner for quest-dev",
            [
                "terraform/config/runner.tf",
                "terraform/config/variables.tf",
                "helm/bitbucket-runner/Chart.yaml",
                "helm/bitbucket-runner/templates/deployment.yaml",
            ],
            task_mode="build",
            task_class="build",
        )
        plan, outcome2, calls2 = _runner_experience(
            2,
            "Create the complete implementation plan in simple bullet points and commit it in the branch",
            ["docs/bitbucket-runner-plan.md"],
            task_mode="think",
            task_class="think",
        )
        for experience, outcome, calls in (
            (implementation, outcome1, calls1),
            (plan, outcome2, calls2),
        ):
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)
            compile_for_experience(store, experience, now=100 + experience.created_at)

        area = next(
            reflex for reflex in store.list_reflexes(states=("learned", "proven"), limit=100)
            if reflex.family == "area:bitbucket-runner"
        )
        assert area.name == "Bitbucket runner work"
        assert area.task_mode == "project"
        assert area.support_count == 2
        assert area.success_count == 2

        matched = match_reflex(
            store,
            "Where is the implementation plan committed?",
            "build",
            "build",
            family_hints={"area:bitbucket-runner"},
        )
        assert matched is not None
        assert matched[0].id == area.id
    finally:
        store.close()


def test_contextual_followup_reuses_shared_runner_area_without_mcp(engine, clock):
    first_session = "runner-session"
    implementation_script = [
        ("Read", {"file_path": "terraform/config/runner.tf"}, True, None),
        ("Edit", {"file_path": "terraform/config/runner.tf"}, True, None),
        ("Edit", {"file_path": "helm/bitbucket-runner/Chart.yaml"}, True, None),
        ("Bash", {"command": "helm lint helm/bitbucket-runner"}, True, None),
    ]
    outcome, _ = run_task(
        engine,
        clock,
        first_session,
        "Add GCP-native Bitbucket Kubernetes runner for quest-dev",
        implementation_script,
    )
    assert outcome.status == "success"

    clock.advance(20)
    engine.prompt(
        "claude-code",
        first_session,
        "No I want the complete implementation plan in very simple bullet points to be created and committed in a branch",
    )
    clock.advance(5)
    engine.tool_start(
        "claude-code",
        first_session,
        "plan-edit",
        "Write",
        {"file_path": "docs/bitbucket-runner-plan.md"},
    )
    clock.advance(2)
    engine.tool_end(
        "claude-code",
        first_session,
        "plan-edit",
        "Write",
        {"file_path": "docs/bitbucket-runner-plan.md"},
        True,
        None,
        400,
    )
    clock.advance(2)
    plan_outcome = engine.stop("claude-code", first_session, assistant_completed=True)
    assert plan_outcome is not None and plan_outcome.status == "success"

    learned = [
        reflex for reflex in engine.store.list_reflexes(states=("learned", "proven"), limit=100)
        if reflex.family == "area:bitbucket-runner"
    ]
    assert len(learned) == 1

    clock.advance(20)
    context = engine.prompt(
        "claude-code",
        first_session,
        "Where is the implementation plan committed?",
    )
    assert context is not None
    assert "Reflex: Bitbucket runner work" in context
    assert "test-first" not in context
    assert "inspect-first" not in context
