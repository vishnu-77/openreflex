from openreflex.learning import regret
from openreflex.models import CandidatePath, Outcome
from openreflex.routing import candidates, classify


def _path(strategy: str, *, score: float, evidence_count: int) -> CandidatePath:
    return CandidatePath(
        task_id="t",
        strategy=strategy,
        steps=[],
        success_probability=0.8,
        time_seconds=100,
        tool_calls=5,
        context_tokens=1000,
        risk=0.1,
        uncertainty=0.2,
        reversibility=0.9,
        evidence_count=evidence_count,
        score=score,
    )


def _outcome(status: str = "success") -> Outcome:
    return Outcome(
        execution_id="e",
        status=status,
        evidence="verified",
        verified=True,
        elapsed_seconds=120,
        tool_calls=7,
        failures=0,
        output_tokens_estimate=1500,
        chosen_strategy="inspect-first",
    )


def test_exploration_tasks_are_classified_and_prefer_inspect_first():
    task = "Map the architecture and explain how both Gradle modules fit together"
    assert classify(task) == "explore"
    paths = candidates("t", "explore", [])
    assert paths[0].strategy == "inspect-first"


def test_regret_is_unavailable_when_all_alternatives_are_prior_only():
    chosen = _path("inspect-first", score=0.4, evidence_count=0)
    alternatives = [
        chosen,
        _path("test-first", score=0.7, evidence_count=0),
        _path("incremental", score=0.6, evidence_count=0),
    ]
    value, alternative, basis = regret(_outcome(), chosen, alternatives)
    assert value is None
    assert alternative is None
    assert basis == "unavailable: no evidenced alternative paths for this task class"


def test_regret_can_compare_against_an_evidenced_alternative():
    chosen = _path("inspect-first", score=0.2, evidence_count=0)
    alternatives = [
        chosen,
        _path("test-first", score=0.7, evidence_count=2),
        _path("incremental", score=0.8, evidence_count=0),
    ]
    value, alternative, basis = regret(_outcome("failure"), chosen, alternatives)
    assert value is not None and value > 0
    assert alternative == "test-first"
    assert "best evidenced alternative test-first" in basis
    assert "evidence n=2" in basis
