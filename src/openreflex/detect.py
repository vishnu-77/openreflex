"""Live inefficiency detection driven by the versioned execution policy."""

from dataclasses import dataclass

from .models import Execution, ToolCall
from .policy import Policy, load_policy
from .privacy import PROGRESS
from .routing import Budget


@dataclass(frozen=True)
class Alert:
    kind: str
    severity: float
    detail: str
    level: int = 0


def detect(execution: Execution, calls: list[ToolCall], budget: Budget, now: float, active_seconds: float = 0,
           policy: Policy | None = None) -> list[Alert]:
    cfg = policy or load_policy()
    values = cfg.table("detectors")
    severity = cfg.table("detectors.severity")
    alerts: list[Alert] = []
    finished = [c for c in calls if c.status != "running"]

    repeat_window = int(values["recent_repeat_window"])
    recent = calls[-repeat_window:]
    counts: dict[str, int] = {}
    for call in recent:
        counts[call.fingerprint] = counts.get(call.fingerprint, 0) + 1
    repeated = max(counts.values(), default=0)
    if repeated >= int(values["repeat_threshold"]):
        name = next(c.name for c in reversed(recent) if counts[c.fingerprint] == repeated)
        alerts.append(Alert("repeated_action", float(severity["repeated_action"]),
                            f"the same {name} call ran {repeated}x in the last {len(recent)} calls"))

    streak = 0
    for call in reversed(finished):
        if call.status != "failure":
            break
        streak += 1
    signature_window = int(values["failure_signature_window"])
    same_signature = [c.error_signature for c in finished[-signature_window:]
                      if c.status == "failure" and c.error_signature]
    top_signature = max(set(same_signature), key=same_signature.count, default=None)
    failure_threshold = int(values["failure_loop_threshold"])
    if streak >= failure_threshold:
        alerts.append(Alert("failure_loop", float(severity["failure_loop_streak"]),
                            f"{streak} consecutive tool failures"))
    elif top_signature and same_signature.count(top_signature) >= failure_threshold:
        alerts.append(Alert("failure_loop", float(severity["failure_loop_signature"]),
                            f"\"{top_signature}\" recurred {same_signature.count(top_signature)}x "
                            f"in {signature_window} calls"))

    since_progress = [c for c in calls if c.started_at > execution.last_progress_at]
    idle = now - execution.last_progress_at
    implementing = any(c.category in PROGRESS for c in calls)
    stagnation_calls = int(values["stagnation_calls"])
    threshold = stagnation_calls if implementing else round(float(values["exploration_stagnation_multiplier"])
                                                             * stagnation_calls)
    enough_for_time = len(since_progress) >= int(values["minimum_stagnation_calls_with_time"])
    if len(since_progress) >= threshold or (
        implementing and idle >= float(values["stagnation_seconds"]) and enough_for_time
    ):
        kinds = sorted({c.category for c in since_progress})
        alerts.append(Alert("stagnation", float(severity["stagnation"]),
                            f"{len(since_progress)} calls over {idle / 60:.0f} min without a successful edit or check "
                            f"(only {', '.join(kinds)})"))

    if execution.output_tokens_estimate > budget.context_tokens or execution.compactions:
        reason = "context was compacted" if execution.compactions else \
            f"~{execution.output_tokens_estimate // 1000}k tokens of tool output " \
            f"(budget ~{int(budget.context_tokens) // 1000}k)"
        alerts.append(Alert("context_growth", float(severity["context_growth"]), reason))

    # Budget.usage, as the verdict uses it; reading time only counts once implementing, since exploration is slow by
    # nature. Recent edits no longer mute it: an agent can be busy and still far past what the task was worth.
    used = budget.usage(active_seconds if implementing else 0, len(calls), execution.output_tokens_estimate)
    level = sum(used > float(tier) for tier in values["over_budget_tiers"]) - 1
    # First-tier overrun driven by tool output is exactly what context_growth reports, with more specific advice.
    token_driven = execution.output_tokens_estimate / budget.context_tokens >= used
    if level > 0 or (level == 0 and not (token_driven and any(a.kind == "context_growth" for a in alerts))):
        detail = (f"{used:.0%} of the execution budget ({len(calls)}/{budget.tool_calls:.0f} calls, "
                  f"{active_seconds / 60:.0f}/{budget.seconds / 60:.0f} min, "
                  f"~{execution.output_tokens_estimate // 1000}k/{budget.context_tokens / 1000:.0f}k tokens of tool output)")
        alerts.append(Alert("over_budget", float(severity["over_budget"]) + level * float(values["over_budget_escalation"]),
                            detail, level))
    return alerts


def select(execution: Execution, alerts: list[Alert], now: float, policy: Policy | None = None) -> Alert | None:
    cfg = policy or load_policy()
    if now - execution.last_alert_at < cfg.number("detectors.cooldown_seconds"):
        return None
    fresh = [a for a in alerts if a.kind not in execution.alerts or
             (a.kind == "context_growth" and execution.alerts.count(a.kind) < 1 + min(execution.compactions, 1)) or
             (a.kind == "over_budget" and execution.alerts.count(a.kind) <= a.level)]
    return max(fresh, key=lambda a: a.severity, default=None)
