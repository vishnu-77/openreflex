"""Explainable execution decisions and compact user-facing recaps."""

from __future__ import annotations

from dataclasses import fields, asdict, dataclass, field
from typing import Iterable

from .models import CandidatePath, Execution, Experience, Task
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
    model_tokens: int | None = None
    token_usage: dict[str, int | float] = field(default_factory=dict)
    reflex_name: str | None = None
    note: str = ""  # one plain line: the file a known fix names (start) or what was learned (complete)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionSnapshot":
        known = {f.name for f in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}  # newer writers may add fields
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
                  expected_regret: float | None = None, model_tokens: int | None = None,
                  token_usage: dict[str, int | float] | None = None,
                  reflex_name: str | None = None) -> DecisionSnapshot:
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
            elapsed_seconds=elapsed_seconds, outcome=outcome, model_tokens=model_tokens,
            token_usage=token_usage or {}, reflex_name=reflex_name,
        )

    components = score_components(best, paths, experiences, policy)
    score = reflex_score(components, policy)
    alternatives = [path for path in paths if path.strategy != best.strategy]
    next_best = max(alternatives, key=lambda path: path.score, default=None)
    ranked = sorted(components.items(), key=lambda item: (-item[1], item[0]))
    reason_codes = [name for name, _ in ranked[:3]]
    completion_regret = expected_regret if phase == "complete" else (best.expected_regret if expected_regret is None else expected_regret)
    return DecisionSnapshot(
        timestamp=now, phase=phase, action=action, policy_version=policy.version, policy_sources=policy.sources,
        strategy=best.strategy, next_best_strategy=next_best.strategy if next_best else None,
        reflex_score=score, success_probability=best.success_probability,
        decision_confidence=components["confidence"], evidence_count=len(experiences),
        evidence_quality=components["evidence"], evidence_relevance=components["relevance"],
        route_advantage=components["route_advantage"], uncertainty=best.uncertainty,
        expected_regret=completion_regret,
        estimated_tool_calls=best.tool_calls, estimated_tokens=best.context_tokens, context_tokens=context_tokens,
        budget_used=max(0.0, budget_used), budget_pressure=_clamp(budget_used),
        score_components=components, reason_codes=reason_codes, visibility=_visibility(phase, event, policy),
        event=event, actual_tool_calls=actual_tool_calls, actual_tokens=actual_tokens,
        elapsed_seconds=elapsed_seconds, outcome=outcome, model_tokens=model_tokens,
        token_usage=token_usage or {}, reflex_name=reflex_name,
    )


def render_recap(snapshot: DecisionSnapshot, previous: DecisionSnapshot | None = None) -> str:
    if snapshot.phase == "complete":
        # Missing completion evidence is an internal epistemic state, not a user-facing failure.
        # Keep it available in status/trace, but stay silent in the ambient Stop surface.
        if snapshot.outcome == "unknown":
            return ""

        state = "COMPLETE" if snapshot.outcome == "success" else "FAILED"
        summary = [snapshot.outcome or "", snapshot.strategy or ""]
        if snapshot.actual_tool_calls is not None:
            summary.append(f"{snapshot.actual_tool_calls} calls")
        if snapshot.expected_regret is not None and snapshot.next_best_strategy:
            summary.append(f"regret {snapshot.expected_regret:.2f} vs {snapshot.next_best_strategy}")
        lines = [f"↺ OpenReflex · {state}", " · ".join(part for part in summary if part)]
        if snapshot.note:
            lines.append(snapshot.note)
        return "\n".join(lines)

    delta = ""
    if previous is not None and previous.reflex_score != snapshot.reflex_score:
        change = snapshot.reflex_score - previous.reflex_score
        delta = f" {'↑' if change > 0 else '↓'}{abs(change)}"
    first = f"↺ OpenReflex · {snapshot.reflex_score}{delta}"
    if snapshot.phase == "start":
        success = "?" if snapshot.success_probability is None else f"{snapshot.success_probability:.0%}"
        calls = "?" if snapshot.estimated_tool_calls is None else f"~{snapshot.estimated_tool_calls:.0f} calls"
        label = snapshot.strategy or "working approach"
        lines = [first, f"{snapshot.evidence_count} experiences · {label} {success} · {calls} · "
                        f"+{snapshot.context_tokens} context tokens"]
        if snapshot.note:
            lines.append(snapshot.note)
        return "\n".join(lines)

    parts = [f"{snapshot.actual_tool_calls} calls"] if snapshot.actual_tool_calls is not None else []
    parts.append(f"budget {snapshot.budget_used:.0%}")
    action = snapshot.action
    if action == "pivot" and snapshot.strategy:
        action += f" → {snapshot.strategy}"  # a pivot's snapshot is of the path it pivots to
    return f"{first}\n{' · '.join(parts + [action])}"


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


def render_paths(execution: Execution, task: Task, paths: list[CandidatePath]) -> str:
    best = min(paths, key=lambda p: (p.dominated_by is not None, not p.within_limits, -p.score))
    chosen = next((p for p in paths if p.id == execution.chosen_path_id), None)
    recommended = next((p for p in paths if p.id == execution.recommended_path_id), None)
    lines = ["OPENREFLEX / PATHS", "",
             f"Task           {task.task_class} - {task.description}",
             f"Recommended    {recommended.strategy if recommended else 'n/a'}"]
    if chosen is not None:
        lines.append(f"Followed       {chosen.strategy} "
                      f"({'inferred from tool calls' if execution.chosen_inferred else 'explicit'})")
    else:
        lines.append("Followed       not yet determined" +
                      (" (execution still running)" if execution.ended_at is None
                       else " (no strategy could be inferred from tool-call evidence)"))
    lines += ["", "CANDIDATES"]
    for path in paths:
        tags = ", ".join(tag for tag in (("recommended" if path is recommended else None),
                                          ("followed" if path is chosen else None)) if tag)
        note = (f"dominated by {path.dominated_by}" if path.dominated_by else
                "over your limit" if not path.within_limits else
                (f"{path.score:+.2f} vs {best.score:+.2f}" if path is not best else ""))
        suffix = " ".join(part for part in (f"[{tags}]" if tags else "", f"({note})" if note else "") if part)
        lines.append(f"  {path.strategy:<14} score {path.score:+.2f}  success {path.success_probability:.0%}  "
                      f"~{path.tool_calls:.0f} calls  ~{path.time_seconds / 60:.0f} min  risk {path.risk:.2f} "
                      f"{suffix}".rstrip())
    return "\n".join(lines)
