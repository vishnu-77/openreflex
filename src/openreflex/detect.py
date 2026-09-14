"""Live inefficiency detection. Pure functions over the current execution's minimized telemetry.

Alerts are deliberately conservative: each kind fires at most once per execution (context growth may
escalate once more after compaction), and any alert respects a cooldown, so the agent is only
interrupted when replanning is justified by evidence rather than by a single slow step.
"""

from dataclasses import dataclass

from .models import Execution, ToolCall
from .privacy import PROGRESS
from .routing import Budget

COOLDOWN_SECONDS = 180
REPEAT_THRESHOLD = 3
FAILURE_LOOP_THRESHOLD = 3
STAGNATION_CALLS = 15
STAGNATION_SECONDS = 600


@dataclass(frozen=True)
class Alert:
    kind: str
    severity: float
    detail: str


def detect(execution: Execution, calls: list[ToolCall], budget: Budget, now: float, active_seconds: float = 0) -> list[Alert]:
    alerts: list[Alert] = []
    finished = [c for c in calls if c.status != "running"]

    recent = calls[-10:]
    counts: dict[str, int] = {}
    for call in recent:
        counts[call.fingerprint] = counts.get(call.fingerprint, 0) + 1
    repeated = max(counts.values(), default=0)
    if repeated >= REPEAT_THRESHOLD:
        name = next(c.name for c in reversed(recent) if counts[c.fingerprint] == repeated)
        alerts.append(Alert("repeated_action", 0.6, f"the same {name} call ran {repeated}x in the last {len(recent)} calls"))

    streak = 0
    for call in reversed(finished):
        if call.status != "failure":
            break
        streak += 1
    same_signature = [c.error_signature for c in finished[-5:] if c.status == "failure" and c.error_signature]
    top_signature = max(set(same_signature), key=same_signature.count, default=None)
    if streak >= FAILURE_LOOP_THRESHOLD:
        alerts.append(Alert("failure_loop", 0.9, f"{streak} consecutive tool failures"))
    elif top_signature and same_signature.count(top_signature) >= FAILURE_LOOP_THRESHOLD:
        alerts.append(Alert("failure_loop", 0.8, f"\"{top_signature}\" recurred {same_signature.count(top_signature)}x in 5 calls"))

    since_progress = [c for c in calls if c.started_at > execution.last_progress_at]
    idle = now - execution.last_progress_at
    # Exploration and Q&A legitimately read without editing; only judge stagnation once implementation has
    # begun (an edit or check was attempted), or when reading has gone on far longer than any plan needs.
    implementing = any(c.category in PROGRESS for c in calls)
    threshold = STAGNATION_CALLS if implementing else 2 * STAGNATION_CALLS
    if len(since_progress) >= threshold or (implementing and idle >= STAGNATION_SECONDS and len(since_progress) >= 5):
        kinds = sorted({c.category for c in since_progress})
        alerts.append(Alert("stagnation", 0.7, f"{len(since_progress)} calls over {idle / 60:.0f} min without a "
                                               f"successful edit or check (only {', '.join(kinds)})"))

    if execution.output_tokens_estimate > budget.context_tokens or execution.compactions:
        reason = "context was compacted" if execution.compactions else \
            f"~{execution.output_tokens_estimate // 1000}k tokens of tool output (budget ~{int(budget.context_tokens) // 1000}k)"
        alerts.append(Alert("context_growth", 0.5, reason))

    recent_progress = any(c.category in PROGRESS and c.status == "success" for c in calls[-8:])
    # The time budget, like stagnation, only applies once implementation has begun: reading can take a while.
    if not recent_progress and (len(calls) > budget.tool_calls or (implementing and active_seconds > budget.seconds)):
        detail = (f"{len(calls)} tool calls (budget ~{budget.tool_calls:.0f})" if len(calls) > budget.tool_calls
                  else f"{active_seconds / 60:.0f} min of work (budget ~{budget.seconds / 60:.0f} min)")
        alerts.append(Alert("over_budget", 0.5, detail))
    return alerts


def select(execution: Execution, alerts: list[Alert], now: float) -> Alert | None:
    """Choose at most one alert that is new for this execution and outside the cooldown."""
    if now - execution.last_alert_at < COOLDOWN_SECONDS:
        return None
    fresh = [a for a in alerts if a.kind not in execution.alerts or
             (a.kind == "context_growth" and execution.alerts.count(a.kind) < 1 + min(execution.compactions, 1))]
    return max(fresh, key=lambda a: a.severity, default=None)
