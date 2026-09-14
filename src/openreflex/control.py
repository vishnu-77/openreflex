"""Budget-aware execution control: is more computation on the current path still worth it?

The current path's success estimate starts from its planned probability and is updated with Bayes' rule as
the task runs. A tool call that makes no progress, and more so a failure, is likelier on a path that will not
work than on one that will, so each lowers the odds. Failures also weigh, more lightly, on the alternatives,
since some causes (a broken environment, a wrong assumption about the task) defeat any approach.

The marginal value of continuing is the success the path can still deliver minus the cost of the work it is
expected to need; pivoting is valued the same way for the best untried alternative that no other untried one
dominates, charged
the part of its work a fresh start repeats; stopping is the zero point. Work past the budget costs more per
unit. A verdict other than "continue" is only acted on when a detector has already found trouble.
"""

import math
from dataclasses import dataclass

from .models import CandidatePath, Execution, ToolCall
from .privacy import PROGRESS
from .routing import Budget, dominates, marginal_cost

SUCCESS_VALUE = 0.55        # utility weight of success, as in routing.utility
IDLE_LIKELIHOOD = 0.85      # P(call without progress | path will succeed) / P(... | path will not)
FAILURE_LIKELIHOOD = 0.6    # the same ratio for a failed call
SHARED_FAILURE_LIKELIHOOD = 0.85  # how much each failure also counts against the alternatives
PIVOT_REUSE = 0.3           # most of an alternative's work that exploration so far can already cover
PIVOT_MARGIN = 0.03         # a pivot must beat continuing by this much utility
MIN_REMAINING = 0.3         # continuing always needs at least this share of the path's expected work


@dataclass(frozen=True)
class Verdict:
    action: str                     # "continue", "pivot" or "stop"
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


def _update(probability: float, likelihood_ratio: float) -> float:
    probability = min(max(probability, 1e-6), 1 - 1e-6)
    odds = probability / (1 - probability) * likelihood_ratio
    return odds / (1 + odds)


def assess(execution: Execution, calls: list[ToolCall], current: CandidatePath | None,
           alternatives: list[CandidatePath], budget: Budget, active_seconds: float, since: float,
           tried: set[str] = frozenset()) -> Verdict:
    """Verdict for the execution so far. `since` is when evidence against the current path starts counting:
    the last progress, or the moment the path was switched to. `tried` strategies are not offered again."""
    finished = [c for c in calls if c.status != "running"]
    recent = [c for c in finished if c.started_at > since]
    failures = sum(c.status == "failure" for c in recent)
    idle = sum(c.status == "success" and c.category not in PROGRESS for c in recent)
    used = budget.usage(active_seconds, len(calls), execution.output_tokens_estimate)
    overrun = max(1.0, used)

    prior = current.success_probability if current else 0.5
    estimate = _update(prior, IDLE_LIKELIHOOD ** idle * FAILURE_LIKELIHOOD ** failures)
    expected_calls = current.tool_calls if current else 20.0
    remaining = max(expected_calls - len(calls), MIN_REMAINING * expected_calls) / max(expected_calls, 1.0)
    value_continue = SUCCESS_VALUE * estimate - overrun * marginal_cost(
        (current.time_seconds if current else 600) * remaining, expected_calls * remaining,
        (current.context_tokens if current else 6000) * remaining)

    total_failures = sum(c.status == "failure" for c in finished)
    # Pivot options are compared with each other, not with the current path: its planning-time estimates are
    # exactly what the evidence in this task is overturning.
    pool = [p for p in alternatives if p.within_limits and p.strategy not in tried
            and not (current and p.strategy == current.strategy)]
    best, best_estimate, best_value = None, None, None
    for path in pool:
        if any(dominates(other, path) for other in pool if other is not path):
            continue
        path_estimate = _update(path.success_probability, SHARED_FAILURE_LIKELIHOOD ** total_failures)
        repeat = 1 - min(PIVOT_REUSE, len(calls) / max(path.tool_calls, 1.0))
        value = SUCCESS_VALUE * path_estimate - overrun * marginal_cost(
            path.time_seconds * repeat, path.tool_calls * repeat, path.context_tokens * repeat)
        if best_value is None or value > best_value:
            best, best_estimate, best_value = path, path_estimate, value

    if best_value is not None and best_value > value_continue + PIVOT_MARGIN and best_value > 0:
        action = "pivot"
    elif value_continue <= 0 and (best_value is None or best_value <= 0) and used >= 1:
        action = "stop"
    else:
        action = "continue"
    return Verdict(action, current.strategy if current else None, round(estimate, 4), round(value_continue, 4),
                   best, None if best_estimate is None else round(best_estimate, 4),
                   None if best_value is None else round(best_value, 4), round(used, 3))


def pivots(execution: Execution) -> list[tuple[str, str, int]]:
    """(from, to, call count) for each pivot recommended so far; verdicts read "pivot:<from>><to>@<calls>"."""
    found = []
    for verdict in execution.verdicts:
        head, _, count = verdict.rpartition("@")
        if head.startswith("pivot:") and ">" in head and count.isdigit():
            source, _, target = head[len("pivot:"):].partition(">")
            found.append((source, target, int(count)))
    return found


def switch_time(execution: Execution, calls: list[ToolCall]) -> float:
    """When the path last changed: the call at which the latest pivot was recommended."""
    history = pivots(execution)
    if not history or not calls:
        return -math.inf
    return calls[max(1, min(history[-1][2], len(calls))) - 1].started_at
