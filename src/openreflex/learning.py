"""Post-execution analysis: infer what happened, estimate Execution Regret, extract lessons.

Everything here is deterministic and works only from minimized telemetry (categories, statuses,
project-relative paths, error signatures) - never from prompts' surrounding transcript or file contents.
"""

import hashlib
from collections import Counter

from .models import CandidatePath, Execution, Experience, Lesson, Outcome, Status, ToolCall
from .privacy import VERIFICATION
from .routing import utility

IDLE_GAP_CAP = 300  # waiting on the user between turns is not execution time


def active_seconds(execution: Execution, calls: list[ToolCall], now: float) -> float:
    stamps = sorted([execution.started_at] + [c.started_at for c in calls] + [c.ended_at for c in calls if c.ended_at])
    end = execution.ended_at or now
    if not calls:
        return max(0.0, min(end - execution.started_at, IDLE_GAP_CAP))
    return sum(min(b - a, IDLE_GAP_CAP) for a, b in zip(stamps, stamps[1:])) + min(max(0.0, end - stamps[-1]), 60)


def infer_status(calls: list[ToolCall]) -> tuple[Status, str]:
    """Only verification after the last edit counts as evidence; anything else stays unknown."""
    last_edit = max((i for i, c in enumerate(calls) if c.category == "edit" and c.status == "success"), default=-1)
    checks = [c for c in calls[last_edit + 1:] if c.category in VERIFICATION and c.status != "running"]
    if not checks:
        if last_edit == -1 and calls and all(c.status == "success" for c in calls):
            return "unknown", "no edits or verification observed (likely exploration)"
        return "unknown", "no verification observed after the last edit"
    last = checks[-1]
    if last.status == "success":
        return "success", f"{last.category} passed after the last edit (inferred)"
    return "failure", f"last {last.category} after the last edit failed (inferred)"


def infer_strategy(calls: list[ToolCall]) -> str | None:
    categories = [c.category for c in calls]
    if "edit" not in categories:
        return None
    first_edit = categories.index("edit")
    if any(c in {"test"} for c in categories[:first_edit]):
        return "test-first"
    # Several edit bursts separated by *passing* checks means the work was sliced; edits after a failing
    # check are fix iterations within one slice, not new slices.
    bursts, in_edit = 0, False
    for call in calls:
        if call.category == "edit" and not in_edit:
            bursts += 1
            in_edit = True
        elif call.category in VERIFICATION and call.status == "success":
            in_edit = False
    return "incremental" if bursts >= 3 else "inspect-first"


def realized_utility(status: Status, seconds: float, calls: int, tokens: int, path: CandidatePath | None) -> float:
    risk = path.risk if path else 0.15
    reversibility = path.reversibility if path else 0.9
    return utility(1.0 if status == "success" else 0.0, seconds, calls, tokens, risk, 0, reversibility)


def regret(outcome: Outcome, chosen: CandidatePath | None, alternatives: list[CandidatePath]) -> tuple[float | None, str | None, str]:
    """Execution Regret = best plausible alternative's expected utility − the chosen path's realized utility.

    Returns (regret, best_alternative, basis). Regret is withheld when the outcome is unknown, because a
    guessed outcome would make the number look precise while meaning nothing.
    """
    if chosen is None:
        return None, None, "unavailable: no chosen path (declared or inferred)"
    if outcome.status == "unknown":
        return None, None, "unavailable: outcome not verified"
    realized = realized_utility(outcome.status, outcome.elapsed_seconds, outcome.tool_calls,
                                outcome.output_tokens_estimate, chosen)
    others = [p for p in alternatives if p.strategy != chosen.strategy]
    if not others:
        return None, None, "unavailable: no alternative paths"
    # Priors are useful for planning, but they are not retrospective counterfactual evidence.
    # Do not turn "no evidence that an alternative was better" into a precise zero-regret claim.
    evidenced = [p for p in others if p.evidence_count > 0]
    if not evidenced:
        return None, None, "unavailable: no evidenced alternative paths for this task class"
    best = max(evidenced, key=lambda p: p.score)
    value = max(0.0, best.score - realized)
    basis = (f"chosen {chosen.strategy} realized U={realized:.3f}; best evidenced alternative {best.strategy} "
             f"expected U={best.score:.3f} (evidence n={best.evidence_count})")
    return round(value, 4), best.strategy, basis


def _key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def extract_lessons(experience: Experience, calls: list[ToolCall], resolutions: list[tuple[ToolCall, ToolCall]],
                    alerts: list[str]) -> list[Lesson]:
    lessons: list[Lesson] = []
    task_class = experience.task_class

    def add(kind: str, key_parts: tuple[str, ...], text: str, confidence: float, evidence: list[str]):
        lessons.append(Lesson(experience_id=experience.id, key=_key(kind, task_class, *key_parts), kind=kind,
                              task_class=task_class, text=text[:280], confidence=round(min(confidence, 0.95), 3),
                              evidence_ids=[experience.id, *evidence][:20]))

    if experience.strategy and experience.status != "unknown":
        verb = "worked" if experience.status == "success" else "did not work"
        add("strategy", (experience.strategy, experience.status),
            f"{experience.strategy} {verb} for a similar {task_class} task "
            f"({experience.tool_calls} tool calls, {experience.elapsed_seconds / 60:.0f} min).",
            0.6 if experience.status == "success" else 0.5, [])

    edited = sorted({f for c in calls if c.category == "edit" and c.status == "success" for f in c.files})
    if experience.status == "success" and edited:
        shown = ", ".join(edited[:5])
        add("files", tuple(edited[:5]), f"Changes for this kind of task landed in: {shown}.", 0.55, [])

    for failed, fixed in resolutions:
        if failed.error_signature:
            where = f" in {', '.join(fixed.files[:2])}" if fixed.files else ""
            action = "an edit" if fixed.category == "edit" else f"a changed {fixed.category} step"
            add("resolution", (failed.error_signature,),
                f"\"{failed.error_signature}\" (from {failed.category}) was resolved by {action}{where}.",
                0.6, [failed.id, fixed.id])

    signatures = Counter(c.error_signature for c in calls if c.status == "failure" and c.error_signature)
    for signature, count in signatures.items():
        if count >= 3:
            add("failure-loop", (signature,),
                f"Retrying after \"{signature}\" looped {count}x; change approach after the second failure.", 0.55, [])

    if "repeated_action" in alerts:
        add("repetition", ("repeated_action",), "The same tool call was repeated verbatim; its result was reusable.",
            0.4, [])
    if "context_growth" in alerts and experience.output_tokens_estimate > 20000:
        add("context", ("context_growth",),
            "Large tool outputs dominated context; use targeted reads/searches and filtered command output.", 0.45, [])
    return lessons


def resolutions(calls: list[ToolCall]) -> list[tuple[ToolCall, ToolCall]]:
    """Pairs a failing call with what resolved it: the last successful edit before the same category next
    succeeded, or that success itself when nothing was edited in between (e.g. a corrected command)."""
    pairs, open_failures, last_edit = [], {}, None
    for call in calls:
        if call.status == "failure":
            open_failures.setdefault(call.category, (call, last_edit))
        elif call.status == "success":
            if call.category in open_failures:
                failed, edit_at_failure = open_failures.pop(call.category)
                if last_edit is not None and last_edit is not edit_at_failure:
                    pairs.append((failed, last_edit))
                elif failed.fingerprint != call.fingerprint:
                    pairs.append((failed, call))
            if call.category == "edit":
                last_edit = call
    return pairs
