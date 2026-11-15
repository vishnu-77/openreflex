"""Product and routing metrics computed from one project's local Experience Graph.

These are measurements of what was captured, not controlled experiments: comparisons between tasks that
did and did not receive prior experience are observational and confounded by task mix. The benchmark
module provides the controlled (simulated) comparison.
"""

import math
import time
from collections import Counter, defaultdict
from statistics import mean, variance

from .engine import HARNESS_MESSAGE, MARKERS, Engine
from .models import evidence_level_of, is_verified
from .learning import realized_utility
from .reflexes import reflex_summary

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


def _counted(store):
    """Tasks, executions and experiences of work a person asked for.

    Versions before 0.10.0 stored task notifications and subagent hand-backs as tasks of their own; they are left
    out by the rule new tasks already follow, so status and the pane count the same tasks.
    """
    every_task = store.list("Task", limit=100_000)
    machine = {t.id for t in every_task if HARNESS_MESSAGE.match((t.description or "").strip())}
    tasks = [t for t in every_task if t.id not in machine]
    executions = [e for e in store.list("Execution", limit=100_000) if e.task_id not in machine]
    experiences = sorted((x for x in store.list("Experience", limit=100_000) if x.task_id not in machine),
                         key=lambda x: x.created_at)
    return tasks, executions, experiences


# Fewer held-out tasks than this per side and the pane says the comparison has too little data to read.
MIN_HOLDOUT_SIDE = 30


def evidence(engine: Engine) -> dict:
    """Whether OpenReflex's memory is being used and checked, for the pane: observations, not proof of benefit.

    - outcomes: by evidence level (ADR 0001), never merged: independently verified, check passed, agent reported,
      inferred (the task ended with a known status and nothing stronger) and unknown.
    - recall: tasks shown past experiences, and of those, tasks that then touched a file those experiences touched.
    - holdout: shown against held-out substantial tasks, and the tool-call change once both sides are large enough.
    """
    store = engine.store
    tasks, executions, experiences = _counted(store)
    substantial = {t.id for t in tasks if t.substantial}
    outcomes = {o.execution_id: o for o in store.list("Outcome", limit=100_000)}
    levels = Counter()
    for execution in executions:
        outcome = outcomes.get(execution.id)
        if execution.task_id not in substantial or outcome is None:
            continue
        level = evidence_level_of(outcome)
        levels["unknown" if level == "observed" and outcome.status == "unknown" else
               "inferred" if level == "observed" else level] += 1

    contexts = {c.task_id: c for c in store.list("Context", limit=100_000)}
    files_of = {x.id: set(x.files) for x in experiences}
    mine = [x for x in experiences if x.task_id in substantial]
    recalled_of, sources_of = {}, {}
    for x in mine:
        context = contexts.get(x.task_id)
        if context is not None and context.injected and context.experience_ids:
            sources_of[x.id] = set(context.experience_ids)
            recalled_of[x.id] = set().union(*(files_of.get(i, set()) for i in context.experience_ids))
    # Use is judged by files, so it can be judged only when the recall named files and the task touched some.
    checkable = [x for x in mine if recalled_of.get(x.id) and x.files]
    used = sum(1 for x in checkable if recalled_of[x.id] & set(x.files))
    # Chance: how often a task shown nothing touched the files a recall named anyway, averaged over recalls. The
    # recalled experiences themselves are left out: their own tasks touched those files by definition.
    unshown = [x for x in mine if x.id not in recalled_of and x.files]
    rates = []
    for x in checkable:
        others = [set(u.files) for u in unshown if u.id not in sources_of[x.id]]
        if others:
            rates.append(sum(1 for files in others if recalled_of[x.id] & files) / len(others))
    chance = round(mean(rates), 3) if rates else None

    holdout_of = {e.id: e.holdout for e in executions if e.task_id in substantial}
    sides = {True: [], False: []}
    for x in mine:
        if x.execution_id in holdout_of:
            sides[holdout_of[x.execution_id]].append(x.tool_calls)

    # First-file pointers (Phase B): "used" = the task then touched a pointed file. Held-out tasks record what they
    # would have been shown, so their rate of touching those files anyway is the comparison.
    files_of_execution = {x.execution_id: set(x.files) for x in mine}
    pointers = {"shown": 0, "used": 0, "held_out": 0, "held_out_used": 0}
    for execution in executions:
        if execution.task_id not in substantial:
            continue
        marker = next((a for a in execution.alerts if a.startswith("pointer:")), "pointer:")
        pointed = {p for p in marker[len("pointer:"):].split("|") if p}
        if not pointed:
            continue
        side = "held_out" if execution.holdout else "shown"
        pointers[side] += 1
        pointers[side + "_used" if side == "held_out" else "used"] += bool(
            pointed & files_of_execution.get(execution.id, set()))
    return {
        "tasks": len(substantial),
        "outcomes": {key: levels[key] for key in
                     ("independently_verified", "check_passed", "agent_reported", "inferred", "unknown")},
        "recall": {"shown": len(recalled_of), "checkable": len(checkable), "used": used, "chance": chance},
        "pointers": pointers,
        "holdout": {"shown": len(sides[False]), "held_out": len(sides[True]), "min_side": MIN_HOLDOUT_SIDE,
                    **_typical_change(sides[False], sides[True])},
    }


def _typical_change(shown: list[int], held: list[int]) -> dict:
    """Change in typical tool calls, shown against held out, with a 95% interval; none until both sides are large.

    Tool calls are skewed, so the comparison is of means of log(1 + calls): a change in the geometric mean.
    """
    if min(len(shown), len(held)) < MIN_HOLDOUT_SIDE:
        return {"tool_call_change": None, "low": None, "high": None}
    a, b = [math.log1p(v) for v in shown], [math.log1p(v) for v in held]
    diff = mean(a) - mean(b)
    spread = 1.96 * math.sqrt(variance(a) / len(a) + variance(b) / len(b))
    return {"tool_call_change": round(math.expm1(diff), 3), "low": round(math.expm1(diff - spread), 3),
            "high": round(math.expm1(diff + spread), 3)}


def project_metrics(engine: Engine, approval_record: dict | None = None, now: float | None = None) -> dict:
    store, now = engine.store, now or time.time()
    tasks, executions, experiences = _counted(store)
    contexts = {c.task_id: c for c in store.list("Context", limit=100_000)}
    reflexes = reflex_summary(store)
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
    reused = [
        t for t in substantial
        if contexts.get(t.id) and (contexts[t.id].experience_ids or contexts[t.id].reflex_id)
    ]

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

    alerts = Counter(a for e in executions for a in e.alerts if not a.startswith(MARKERS))
    alerts["retry_warning"] = sum(1 for e in executions for a in e.alerts if a.startswith("retry:"))
    alerts["known_fix"] = sum(1 for e in executions for a in e.alerts if a.startswith("fix:"))
    verdicts = Counter(v.split(":")[0].split("@")[0] for e in executions for v in e.verdicts)
    # After a pivot or stop, did the task still reach a verified success? (observational)
    advised = [x for x in known if any(v.startswith(("pivot", "stop")) for v in x.verdicts)]
    outcomes_by_execution = {o.execution_id: o for o in store.list("Outcome", limit=100_000)}
    within_budget = [outcomes_by_execution[e.id].tool_calls <= e.budget_tool_calls for e in executions
                     if e.budget_tool_calls and e.id in outcomes_by_execution]
    with_prior_profile, without_prior_profile = profile(with_prior), profile(without_prior)
    reuse_rate = round(len(reused) / len(substantial), 3) if substantial else None

    context_by_task = {task.id: 0 for task in substantial}
    for execution in executions:
        if execution.task_id in context_by_task:
            context_by_task[execution.task_id] = max(
                context_by_task[execution.task_id],
                max(0, int(execution.context_tokens or 0)),
            )
    context_values = list(context_by_task.values())
    context_injected = [value for value in context_values if value > 0]
    observed_model_tokens = sum(experience.model_tokens for experience in experiences if experience.model_tokens > 0)
    diagnostic_mcp_calls = int(store.get_meta("diagnostic_mcp_calls", "0") or 0)
    diagnostic_mcp_tokens = int(store.get_meta("diagnostic_mcp_tokens_estimate", "0") or 0)
    estimated_context_tokens = sum(context_values)
    # Injected text stays in the conversation and is re-read by every later API call, so its cost is its size times
    # the calls that follow. Counting only the calls of the same task makes this a lower bound.
    reread_tokens = sum(int(e.context_tokens or 0) * len(store.usage_for_execution(e.id))
                        for e in executions if e.context_tokens)
    estimated_context_tax = (
        round(reread_tokens / observed_model_tokens, 4)
        if observed_model_tokens > 0 else None
    )

    # The holdout is the only unconfounded comparison: the same kinds of task, assigned by hash, with OpenReflex
    # silent. Only tasks since the holdout began are compared, so older history cannot bias the "shown" side.
    holdout_start = min((e.started_at for e in executions if e.holdout), default=None)
    holdout_by_execution = {e.id: e.holdout for e in executions if holdout_start is not None and e.started_at >= holdout_start}
    compared = [x for x in experiences if x.execution_id in holdout_by_execution
                and getattr(task_by_id.get(x.task_id), "substantial", False)]
    shown_profile = profile([x for x in compared if not holdout_by_execution[x.execution_id]])
    held_profile = profile([x for x in compared if holdout_by_execution[x.execution_id]])

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
        "openreflex_overhead": {
            "estimated_context_tokens": estimated_context_tokens,
            "context_injected_tasks": len(context_injected),
            "zero_injection_tasks": max(0, len(substantial) - len(context_injected)),
            "average_injected_context_tokens": _avg(context_injected),
            "max_injected_context_tokens": max(context_injected, default=0),
            "diagnostic_mcp_calls": diagnostic_mcp_calls,
            "diagnostic_mcp_tokens_estimate": diagnostic_mcp_tokens,
            "observed_model_tokens": observed_model_tokens,
            "estimated_context_reread_tokens": reread_tokens,
            "estimated_context_tax": estimated_context_tax,
            "context_token_method": "estimated from injected characters / configured chars_per_token",
            "diagnostic_token_method": "estimated from MCP result characters / configured chars_per_token",
        },
        "outcomes": {"known": len(known), "verified": sum(1 for e in executions if is_verified(outcomes_by_execution.get(e.id))),
                     "success_rate": _avg(x.status == "success" for x in known)},
        "efficiency_observational": {
            "with_prior_experience": with_prior_profile, "without_prior_experience": without_prior_profile,
            "tool_call_change": _change(without_prior_profile["tool_calls"], with_prior_profile["tool_calls"]),
            "model_token_change": _change(without_prior_profile["model_tokens"], with_prior_profile["model_tokens"]),
            "time_change": _change(without_prior_profile["minutes"], with_prior_profile["minutes"]),
        },
        "holdout": {
            "percent": engine.policy.number("evaluation.holdout_percent"),
            "shown": shown_profile, "held_out": held_profile,
            "model_token_change": _change(held_profile["model_tokens"], shown_profile["model_tokens"]),
            "tool_call_change": _change(held_profile["tool_calls"], shown_profile["tool_calls"]),
        },
        "prevented": {
            "blocked_retries": int(store.get_meta("blocked_retries", "0") or 0),
            "known_fixes_shown": alerts["known_fix"],
            "context_reset_hints": int(store.get_meta("reset_hints", "0") or 0),
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
        "project_reflexes": {
            "visible": reflexes["visible"],
            "project_state": reflexes["project_state"],
            "project_support": reflexes["project_support"],
            "specialised_total": reflexes["specialised_total"],
            "learning": reflexes["learning"],
            "learned": reflexes["learned"],
            "proven": reflexes["proven"],
            "stale": reflexes["stale"],
            "credit_signals": reflexes["credit_signals"],
            "credit_spine_actions": reflexes["credit_spine_actions"],
        },
        "lessons": len(store.list("Lesson", limit=100_000)),
    }
