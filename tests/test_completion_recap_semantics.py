from openreflex.decision import DecisionSnapshot, render_recap


def _snapshot(*, outcome: str, expected_regret: float | None = 0.0) -> DecisionSnapshot:
    return DecisionSnapshot(
        timestamp=1.0,
        phase="complete",
        action="complete",
        policy_version="1.0",
        policy_sources=("defaults",),
        strategy="incremental",
        next_best_strategy="test-first",
        reflex_score=50,
        success_probability=0.5,
        decision_confidence=0.5,
        evidence_count=1,
        evidence_quality=0.5,
        evidence_relevance=0.5,
        route_advantage=0.1,
        uncertainty=0.5,
        expected_regret=expected_regret,
        estimated_tool_calls=4.0,
        estimated_tokens=1000.0,
        context_tokens=0,
        budget_used=0.1,
        budget_pressure=0.1,
        actual_tool_calls=1,
        actual_tokens=0,
        elapsed_seconds=18.0,
        outcome=outcome,
    )


def test_unknown_completion_is_unverified_and_hides_legacy_regret():
    recap = render_recap(_snapshot(outcome="unknown", expected_regret=0.0))
    assert recap.startswith("↺ OpenReflex · UNVERIFIED")
    assert "unknown · incremental" in recap
    assert "regret" not in recap
    assert "vs test-first" not in recap


def test_success_completion_remains_complete_and_can_show_regret():
    recap = render_recap(_snapshot(outcome="success", expected_regret=0.25))
    assert recap.startswith("↺ OpenReflex · COMPLETE")
    assert "success · incremental" in recap
    assert "regret 0.25 vs test-first" in recap


def test_failure_completion_is_labelled_failed():
    recap = render_recap(_snapshot(outcome="failure", expected_regret=0.4))
    assert recap.startswith("↺ OpenReflex · FAILED")
    assert "failure · incremental" in recap
    assert "regret 0.40 vs test-first" in recap


def test_unverified_stop_can_upgrade_to_verified_completion(engine, clock):
    engine.prompt("claude-code", "s", "Fix the Helm deployment values validation failure please")
    engine.take_notice("claude-code", "s")  # consume the start recap

    edit = ("Edit", {"file_path": "charts/app/values.yaml"})
    engine.tool_start("claude-code", "s", "e1", *edit)
    clock.advance(1)
    engine.tool_end("claude-code", "s", "e1", *edit, True)

    first = engine.stop("claude-code", "s")
    assert first.status == "unknown"
    first_recap = engine.take_notice("claude-code", "s")
    assert first_recap.startswith("↺ OpenReflex · UNVERIFIED")

    clock.advance(1)
    verification = ("Bash", {"command": "helm lint charts/app"})
    engine.tool_start("claude-code", "s", "v1", *verification)
    clock.advance(1)
    engine.tool_end("claude-code", "s", "v1", *verification, True)

    second = engine.stop("claude-code", "s")
    assert second.status == "success"
    second_recap = engine.take_notice("claude-code", "s")
    assert second_recap.startswith("↺ OpenReflex · COMPLETE")
    assert "success" in second_recap

    completions = [item for item in engine.store.latest("claude-code", "s").decision_history
                   if item.get("phase") == "complete"]
    assert [item.get("outcome") for item in completions] == ["unknown", "success"]
