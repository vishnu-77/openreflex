"""Product and routing metrics computed from one project's local Experience Graph.

These are measurements of what was captured, not controlled experiments: comparisons between tasks that
did and did not receive prior experience are observational and confounded by task mix. The benchmark
module provides the controlled (simulated) comparison.
"""

import time
from collections import Counter, defaultdict
from statistics import mean

from .engine import Engine
from .learning import realized_utility

WEEK = 604800


def _avg(values) -> float | None:
    values = list(values)
    return round(mean(values), 3) if values else None


def _change(before: float | None, after: float | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return round((after - before) / before, 3)


def retrospective_best(experiences) -> dict[str, str]:
    """Per task class, the strategy with the highest mean realized utility (needs >= 2 known outcomes)."""
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for x in experiences:
        if x.strategy and x.status != "unknown":
            groups[x.task_class][x.strategy].append(
                realized_utility(x.status, x.elapsed_seconds, x.tool_calls, x.output_tokens_estimate, None))
    best = {}
    for task_class, strategies in groups.items():
        eligible = {s: mean(v) for s, v in strategies.items() if len(v) >= 2}
        if eligible:
            best[task_class] = max(eligible, key=eligible.get)
    return best


def project_metrics(engine: Engine, approval_record: dict | None = None, now: float | None = None) -> dict:
    store, now = engine.store, now or time.time()
    tasks = store.list("Task", limit=100_000)
    executions = store.list("Execution", limit=100_000)
    experiences = sorted(store.list("Experience", limit=100_000), key=lambda x: x.created_at)
    contexts = {c.task_id: c for c in store.list("Context", limit=100_000)}
    task_by_id = {t.id: t for t in tasks}
    approved_at = (approval_record or {}).get("approved_at")

    first_task = min((t.started_at for t in tasks), default=None)
    first_session = min(tasks, key=lambda t: t.started_at, default=None)
    first_session_captured = None
    if first_session is not None:
        session_tasks = {t.id for t in tasks if (t.agent, t.session_id) == (first_session.agent, first_session.session_id)}
        first_session_captured = any(x.task_id in session_tasks for x in experiences)

    weeks = {int((e.started_at - (approved_at or first_task or now)) // WEEK) for e in executions}
    weeks_elapsed = int((now - (approved_at or first_task or now)) // WEEK) + 1
    substantial = [t for t in tasks if t.substantial]
    reused = [t for t in substantial if contexts.get(t.id) and contexts[t.id].experience_ids]

    known = [x for x in experiences if x.status != "unknown"]
    with_prior = [x for x in experiences if x.benefited]
    without_prior = [x for x in experiences if not x.benefited]

    def profile(group):
        known_group = [x for x in group if x.status != "unknown"]
        model_token_values = [x.model_tokens for x in group if x.model_tokens > 0]
        return {"n": len(group), "tool_calls": _avg(x.tool_calls for x in group),
                "model_tokens": _avg(model_token_values),
                "tool_output_tokens_estimate": _avg(x.output_tokens_estimate for x in group),
                "minutes": _avg(x.elapsed_seconds / 60 for x in group),
                "success_rate": _avg(x.status == "success" for x in known_group), "known_outcomes": len(known_group)}

    comparisons = [x for x in experiences if x.estimated_regret is not None]
    better_options = [x for x in comparisons if x.estimated_regret and x.estimated_regret > 0]
    comparison_by_class = Counter(x.task_class for x in comparisons)

    best = retrospective_best(experiences)
    agreements = []
    for execution in executions:
        task = task_by_id.get(execution.task_id)
        if task and task.substantial and task.task_class in best and store.exists(execution.recommended_path_id):
            agreements.append(store.get(execution.recommended_path_id).strategy == best[task.task_class])

    alerts = Counter(a for e in executions for a in e.alerts if not a.startswith("retry:"))
    alerts["retry_warning"] = sum(1 for e in executions for a in e.alerts if a.startswith("retry:"))
    verdicts = Counter(v.split(":")[0].split("@")[0] for e in executions for v in e.verdicts)
    # After a pivot or stop, did the task still reach a verified success? (observational)
    advised = [x for x in known if any(v.startswith(("pivot", "stop")) for v in x.verdicts)]
    outcomes_by_execution = {o.execution_id: o for o in store.list("Outcome", limit=100_000)}
    within_budget = [outcomes_by_execution[e.id].tool_calls <= e.budget_tool_calls for e in executions
                     if e.budget_tool_calls and e.id in outcomes_by_execution]
    with_prior_profile, without_prior_profile = profile(with_prior), profile(without_prior)
    reuse_rate = round(len(reused) / len(substantial), 3) if substantial else None
    return {
        "project": str(engine.project),
        "activation": {
            "approved_at": approved_at,
            "seconds_to_first_task": round(first_task - approved_at, 1) if approved_at and first_task else None,
            "first_session_captured": first_session_captured,
        },
        "engagement": {"tasks": len(tasks), "substantial_tasks": len(substantial), "executions": len(executions),
                       "experiences": len(experiences), "active_weeks": len(weeks), "weeks_since_start": weeks_elapsed,
                       "active_week_ratio": round(len(weeks) / weeks_elapsed, 3) if executions else None,
                       "agents": sorted({t.agent for t in tasks})},
        "experience_reuse": {"reuse_rate": reuse_rate,
                             "benefit_rate": reuse_rate,
                             "tasks_with_prior_experience": len(reused)},
        "outcomes": {"known": len(known), "verified": sum(1 for o in store.list("Outcome", limit=100_000) if o.verified),
                     "success_rate": _avg(x.status == "success" for x in known)},
        "efficiency_observational": {
            "with_prior_experience": with_prior_profile, "without_prior_experience": without_prior_profile,
            "tool_call_change": _change(without_prior_profile["tool_calls"], with_prior_profile["tool_calls"]),
            "model_token_change": _change(without_prior_profile["model_tokens"], with_prior_profile["model_tokens"]),
            "time_change": _change(without_prior_profile["minutes"], with_prior_profile["minutes"]),
        },
        "path_check": {"comparisons": len(comparisons), "better_option_found": len(better_options),
                       "by_class": dict(comparison_by_class)},
        "routing": {"retrospective_best": best,
                    "agreement": round(sum(agreements) / len(agreements), 3) if agreements else None,
                    "compared_executions": len(agreements)},
        "live_alerts": dict(alerts),
        "execution_control": {"verdicts": dict(verdicts),
                              "success_after_pivot_or_stop": _avg(x.status == "success" for x in advised),
                              "tasks_within_tool_call_budget": _avg(within_budget)},
        "lessons": len(store.list("Lesson", limit=100_000)),
    }
