"""Explainable execution decisions and compact user-facing recaps."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from .models import CandidatePath, Experience
from .policy import Policy


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class DecisionSnapshot:
    timestamp: float
    phase: str
    action: str
    policy_version: str
    policy_sources: tuple[str, ...]
    strategy: str | None
    next_best_strategy: str | None
    reflex_score: int
    success_probability: float | None
    decision_confidence: float
    evidence_count: int
    evidence_quality: float
    evidence_relevance: float
    route_advantage: float
    uncertainty: float
    expected_regret: float | None
    estimated_tool_calls: float | None
    estimated_tokens: float | None
    context_tokens: int
    budget_used: float
    budget_pressure: float
    score_components: dict[str, float] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    visibility: str = "ambient"
    event: str = ""
    actual_tool_calls: int | None = None
    actual_tokens: int | None = None
    elapsed_seconds: float | None = None
    outcome: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionSnapshot":
        values = dict(data)
        values["policy_sources"] = tuple(values.get("policy_sources") or ())
        return cls(**values)


def score_components(best: CandidatePath, rest: Iterable[CandidatePath], experiences: list[tuple[Experience, float]],
                     policy: Policy) -> dict[str, float]:
    alternatives = [path for path in rest if path.strategy != best.strategy]
    next_best = max(alternatives, key=lambda path: path.score, default=None)
    evidence_strength = _clamp(best.evidence_count / policy.number("score.evidence_saturation"))
    confidence = _clamp(1.0 - best.uncertainty)
    advantage = best.score - next_best.score if next_best is not None else best.score
    route_advantage = _clamp(max(0.0, advantage) / policy.number("score.route_advantage_scale"))
    budget_fit = 1.0 if best.within_limits else 0.0
    relevance_values = [score for _, score in experiences]
    threshold = policy.number("retrieval.threshold")
    mean_relevance = sum(relevance_values) / len(relevance_values) if relevance_values else threshold
    relevance = _clamp((mean_relevance - threshold) / max(1.0 - threshold, policy.number("routing.epsilon")))
    return {
        "evidence": evidence_strength,
        "confidence": confidence,
        "route_advantage": route_advantage,
        "budget_fit": budget_fit,
        "relevance": relevance,
    }


def reflex_score(components: dict[str, float], policy: Policy) -> int:
    weights = {name: float(value) for name, value in policy.table("score.weights").items()}
    total = sum(weights.values())
    weighted = sum(weights.get(name, 0.0) * _clamp(value) for name, value in components.items())
    return round(100.0 * weighted / total)


def _visibility(phase: str, event: str, policy: Policy) -> str:
    if phase == "start" and policy.boolean("visibility.show_start"):
        return "recap"
    if phase == "complete" and policy.boolean("visibility.show_complete"):
        return "recap"
    if phase == "runtime" and event in policy.strings("visibility.runtime_events"):
        return "intervention"
    return "ambient"


def make_snapshot(*, now: float, phase: str, action: str, best: CandidatePath | None,
                  paths: list[CandidatePath], experiences: list[tuple[Experience, float]], policy: Policy,
                  context_tokens: int = 0, budget_used: float = 0.0, event: str = "",
                  actual_tool_calls: int | None = None, actual_tokens: int | None = None,
                  elapsed_seconds: float | None = None, outcome: str | None = None,
                  expected_regret: float | None = None) -> DecisionSnapshot:
    if best is None:
        components = {name: 0.0 for name in policy.table("score.weights")}
        score = reflex_score(components, policy)
        return DecisionSnapshot(
            timestamp=now, phase=phase, action=action, policy_version=policy.version,
            policy_sources=policy.sources, strategy=None, next_best_strategy=None, reflex_score=score,
            success_probability=None, decision_confidence=0.0, evidence_count=len(experiences), evidence_quality=0.0,
            evidence_relevance=0.0, route_advantage=0.0, uncertainty=1.0, expected_regret=expected_regret,
            estimated_tool_calls=None, estimated_tokens=None, context_tokens=context_tokens,
            budget_used=_clamp(budget_used), budget_pressure=_clamp(budget_used), score_components=components,
            reason_codes=[], visibility=_visibility(phase, event, policy), event=event,
            actual_tool_calls=actual_tool_calls, actual_tokens=actual_tokens,
            elapsed_seconds=elapsed_seconds, outcome=outcome,
        )

    components = score_components(best, paths, experiences, policy)
    score = reflex_score(components, policy)
    alternatives = [path for path in paths if path.strategy != best.strategy]
    next_best = max(alternatives, key=lambda path: path.score, default=None)
    ranked = sorted(components.items(), key=lambda item: (-item[1], item[0]))
    reason_codes = [name for name, _ in ranked[:3]]
    return DecisionSnapshot(
        timestamp=now, phase=phase, action=action, policy_version=policy.version, policy_sources=policy.sources,
        strategy=best.strategy, next_best_strategy=next_best.strategy if next_best else None,
        reflex_score=score, success_probability=best.success_probability,
        decision_confidence=components["confidence"], evidence_count=len(experiences),
        evidence_quality=components["evidence"], evidence_relevance=components["relevance"],
        route_advantage=components["route_advantage"], uncertainty=best.uncertainty,
        expected_regret=best.expected_regret if expected_regret is None else expected_regret,
        estimated_tool_calls=best.tool_calls, estimated_tokens=best.context_tokens, context_tokens=context_tokens,
        budget_used=max(0.0, budget_used), budget_pressure=_clamp(budget_used),
        score_components=components, reason_codes=reason_codes, visibility=_visibility(phase, event, policy),
        event=event, actual_tool_calls=actual_tool_calls, actual_tokens=actual_tokens,
        elapsed_seconds=elapsed_seconds, outcome=outcome,
    )


def render_recap(snapshot: DecisionSnapshot, previous: DecisionSnapshot | None = None) -> str:
    if snapshot.phase == "complete":
        summary = []
        if snapshot.outcome:
            summary.append(snapshot.outcome)
        if snapshot.strategy:
            summary.append(snapshot.strategy)

        cost = []
        if snapshot.actual_tool_calls is not None:
            cost.append(f"{snapshot.actual_tool_calls} calls")
        if snapshot.actual_tokens is not None:
            cost.append(f"{snapshot.actual_tokens / 1000:.1f}k tokens")
        if snapshot.elapsed_seconds is not None:
            cost.append(f"{snapshot.elapsed_seconds / 60:.1f}m")

        comparison = None
        if snapshot.expected_regret is not None:
            comparison = f"regret {snapshot.expected_regret:.2f}"
            if snapshot.next_best_strategy:
                comparison += f" vs {snapshot.next_best_strategy}"

        lines = ["↺ OpenReflex · COMPLETE"]
        if summary:
            lines.append(" · ".join(summary))
        if cost:
            lines.append(" · ".join(cost))
        if comparison:
            lines.append(comparison)
        return "\n".join(lines)

    delta = ""
    if previous is not None and previous.reflex_score != snapshot.reflex_score:
        change = snapshot.reflex_score - previous.reflex_score
        delta = f" {'↑' if change > 0 else '↓'}{abs(change)}"
    first = f"↺ OpenReflex · {snapshot.reflex_score}{delta}"
    if snapshot.phase == "start":
        success = "?" if snapshot.success_probability is None else f"{snapshot.success_probability:.0%}"
        calls = "?" if snapshot.estimated_tool_calls is None else f"~{snapshot.estimated_tool_calls:.0f} calls"
        tokens = "?" if snapshot.estimated_tokens is None else f"~{snapshot.estimated_tokens / 1000:.0f}k tokens"
        return (f"{first}\n{snapshot.evidence_count} experiences · {snapshot.strategy or 'unplanned'} {success} · "
                f"{calls} · {tokens} · +{snapshot.context_tokens} context tokens")

    success = "?" if snapshot.success_probability is None else f"{snapshot.success_probability:.0%}"
    message = (f"{first}\n{snapshot.action} · {snapshot.strategy or 'unplanned'} {success} · "
               f"budget {snapshot.budget_used:.0%}")
    if snapshot.next_best_strategy and snapshot.action in {"pivot", "stop"}:
        message += f" · next {snapshot.next_best_strategy}"
    return message


def render_why(snapshot: DecisionSnapshot) -> str:
    lines = ["OPENREFLEX / WHY", "", f"Recommendation  {snapshot.strategy or snapshot.action}",
             f"REFLEX          {snapshot.reflex_score}/100",
             f"SUCCESS         {'n/a' if snapshot.success_probability is None else f'{snapshot.success_probability:.0%}'}",
             f"CONFIDENCE      {snapshot.decision_confidence:.0%}", "", "SIGNALS"]
    for name, value in sorted(snapshot.score_components.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"  {name.replace('_', ' '):<16} {value:.0%}")
    if snapshot.next_best_strategy:
        lines += ["", f"Next best        {snapshot.next_best_strategy}",
                  f"Route advantage  {snapshot.route_advantage:.0%}"]
    lines += ["", f"Policy           {snapshot.policy_version}"]
    return "\n".join(lines)


def render_trace(snapshots: list[DecisionSnapshot]) -> str:
    if not snapshots:
        return "OPENREFLEX / TRACE\n\nNo decision snapshots recorded yet."
    start = snapshots[0].timestamp
    lines = ["OPENREFLEX / TRACE", ""]
    for snapshot in snapshots:
        elapsed = max(0, round(snapshot.timestamp - start))
        minute, second = divmod(elapsed, 60)
        label = snapshot.phase.upper()
        detail = snapshot.action
        if snapshot.strategy:
            detail += f" → {snapshot.strategy}"
        detail += f" · Reflex {snapshot.reflex_score}"
        if snapshot.event:
            detail += f" · {snapshot.event}"
        lines.append(f"{minute:02d}:{second:02d} {label:<9} {detail}")
    return "\n".join(lines)
