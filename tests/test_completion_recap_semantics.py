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
        actual_tool_calls=9,
        actual_tokens=7900,
        elapsed_seconds=84.0,
        outcome=outcome,
        reflex_name="Helm values change",
    )


def test_unknown_completion_is_silent_in_ambient_ui():
    recap = render_recap(_snapshot(outcome="unknown", expected_regret=0.0))
    assert recap == ""


def test_success_completion_is_compact_and_evidence_backed():
    recap = render_recap(_snapshot(outcome="success", expected_regret=0.25))
    assert recap == "↺ OpenReflex · VERIFIED\nHelm values change"
    assert "calls" not in recap
    assert "tokens" not in recap
    assert "Path check" not in recap


def test_failure_completion_is_compact_and_evidence_backed():
    recap = render_recap(_snapshot(outcome="failure", expected_regret=0.4))
    assert recap == "↺ OpenReflex · CHECK FAILED\nHelm values change"
    assert "calls" not in recap
    assert "tokens" not in recap


def test_unknown_stop_stays_internal_then_upgrades_to_visible_verified_completion(engine, clock):
    engine.prompt("claude-code", "s", "Fix the Helm deployment values validation failure please")
    engine.take_notice("claude-code", "s")  # consume the start recap

    edit = ("Edit", {"file_path": "charts/app/values.yaml"})
    engine.tool_start("claude-code", "s", "e1", *edit)
    clock.advance(1)
    engine.tool_end("claude-code", "s", "e1", *edit, True)

    first = engine.stop("claude-code", "s")
    assert first.status == "unknown"
    assert engine.take_notice("claude-code", "s") is None

    completions = [item for item in engine.store.latest("claude-code", "s").decision_history
                   if item.get("phase") == "complete"]
    assert completions[-1]["outcome"] == "unknown"
    assert completions[-1]["visibility"] == "ambient"

    clock.advance(1)
    verification = ("Bash", {"command": "helm lint charts/app"})
    engine.tool_start("claude-code", "s", "v1", *verification)
    clock.advance(1)
    engine.tool_end("claude-code", "s", "v1", *verification, True)

    second = engine.stop("claude-code", "s")
    assert second.status == "success"
    second_recap = engine.take_notice("claude-code", "s")
    assert second_recap == "↺ OpenReflex · VERIFIED\nHelm values change"

    completions = [item for item in engine.store.latest("claude-code", "s").decision_history
                   if item.get("phase") == "complete"]
    assert [item.get("outcome") for item in completions] == ["unknown", "success"]
