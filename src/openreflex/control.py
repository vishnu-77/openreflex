"""Budget-aware execution control driven by the versioned OpenReflex policy."""

import math
from dataclasses import dataclass

from .models import CandidatePath, Execution, ToolCall
from .policy import Policy, load_policy
from .privacy import PROGRESS
from .routing import Budget, dominates, marginal_cost


@dataclass(frozen=True)
class Verdict:
    action: str
    current: str | None
    success_estimate: float
    value_continue: float
    alternative: CandidatePath | None
    alternative_estimate: float | None
    value_pivot: float | None
    budget_used: float

    def summary(self) -> str:
        parts = [f"success estimate ~{self.success_estimate:.0%} on {self.current or 'the current path'}"]
        if self.alternative is not None and self.alternative_estimate is not None:
            parts.append(f"~{self.alternative_estimate:.0%} for {self.alternative.strategy}")
        parts.append(f"budget {self.budget_used:.0%} used")
        return ", ".join(parts)


def _update(probability: float, likelihood_ratio: float, epsilon: float) -> float:
    probability = min(max(probability, epsilon), 1 - epsilon)
    odds = probability / (1 - probability) * likelihood_ratio
    return odds / (1 + odds)


def assess(execution: Execution, calls: list[ToolCall], current: CandidatePath | None,
           alternatives: list[CandidatePath], budget: Budget, active_seconds: float, since: float,
           tried: set[str] = frozenset(), policy: Policy | None = None) -> Verdict:
    cfg = policy or load_policy()
    values = cfg.table("control")
    success_value = float(values["success_value"])
    idle_likelihood = float(values["idle_likelihood_ratio"])
    failure_likelihood = float(values["failure_likelihood_ratio"])
    shared_failure_likelihood = float(values["shared_failure_likelihood_ratio"])
    pivot_reuse = float(values["pivot_reuse"])
    pivot_margin = float(values["pivot_margin"])
    minimum_remaining = float(values["minimum_remaining"])
    epsilon = float(values["probability_epsilon"])

    finished = [c for c in calls if c.status != "running"]
    recent = [c for c in finished if c.started_at > since]
    failures = sum(c.status == "failure" for c in recent)
    idle = sum(c.status == "success" and c.category not in PROGRESS for c in recent)
    used = budget.usage(active_seconds, len(calls), execution.output_tokens_estimate)
    overrun = max(1.0, used)

    prior = current.success_probability if current else float(values["fallback_success_probability"])
    estimate = _update(prior, idle_likelihood ** idle * failure_likelihood ** failures, epsilon)
    expected_calls = current.tool_calls if current else cfg.number("routing.budget.minimum_tool_calls")
    remaining = max(expected_calls - len(calls), minimum_remaining * expected_calls) / max(expected_calls, 1.0)
    value_continue = success_value * estimate - overrun * marginal_cost(
        (current.time_seconds if current else cfg.number("routing.budget.minimum_seconds")) * remaining,
        expected_calls * remaining,
        (current.context_tokens if current else cfg.number("routing.budget.minimum_context_tokens")) * remaining,
        cfg,
    )

    total_failures = sum(c.status == "failure" for c in finished)
    pool = [p for p in alternatives if p.within_limits and p.strategy not in tried
            and not (current and p.strategy == current.strategy)]
    best, best_estimate, best_value = None, None, None
    for path in pool:
        if any(dominates(other, path, cfg) for other in pool if other is not path):
            continue
        path_estimate = _update(path.success_probability, shared_failure_likelihood ** total_failures, epsilon)
        repeat = 1 - min(pivot_reuse, len(calls) / max(path.tool_calls, 1.0))
        value = success_value * path_estimate - overrun * marginal_cost(
            path.time_seconds * repeat, path.tool_calls * repeat, path.context_tokens * repeat, cfg)
        if best_value is None or value > best_value:
            best, best_estimate, best_value = path, path_estimate, value

    if best_value is not None and best_value > value_continue + pivot_margin and best_value > 0:
        action = "pivot"
    elif value_continue <= 0 and (best_value is None or best_value <= 0) and used >= 1:
        action = "stop"
    else:
        action = "continue"
    return Verdict(action, current.strategy if current else None, round(estimate, 4), round(value_continue, 4),
                   best, None if best_estimate is None else round(best_estimate, 4),
                   None if best_value is None else round(best_value, 4), round(used, 3))


def pivots(execution: Execution) -> list[tuple[str, str, int]]:
    found = []
    for verdict in execution.verdicts:
        head, _, count = verdict.rpartition("@")
        if head.startswith("pivot:") and ">" in head and count.isdigit():
            source, _, target = head[len("pivot:"):].partition(">")
            found.append((source, target, int(count)))
    return found


def switch_time(execution: Execution, calls: list[ToolCall]) -> float:
    history = pivots(execution)
    if not history or not calls:
        return -math.inf
    return calls[max(1, min(history[-1][2], len(calls))) - 1].started_at
