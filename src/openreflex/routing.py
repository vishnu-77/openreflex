"""Path planning: retrieve comparable evidence, estimate candidate strategies, keep the Pareto-efficient ones,
fit them to an execution budget, and pick the best by utility.
"""

import hashlib
import math
import os
import re
from dataclasses import dataclass

from .models import CandidatePath, Experience

PRIOR_WEIGHT = 4  # pseudo-runs of the prior behind every estimate, so a single run cannot swing a path
REGRET_WEIGHT = 0.25
DETOUR_ALERTS = {"failure_loop", "stagnation", "over_budget"}

# Objectives a path is judged on, with the direction that is better.
OBJECTIVES = (("success_probability", 1), ("time_seconds", -1), ("tool_calls", -1), ("context_tokens", -1),
              ("risk", -1), ("uncertainty", -1), ("reversibility", 1), ("expected_regret", -1))
EPSILON = 1e-9


def embed(text: str, dimensions: int = 256) -> list[float]:
    """Offline lexical feature hashing, not a pretrained semantic model."""
    vector = [0.0] * dimensions
    words = re.findall(r"[a-z0-9_]{2,}", text.lower())
    for word in words + [a + " " + b for a, b in zip(words, words[1:])]:
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        vector[int.from_bytes(digest[:4], "little") % dimensions] += 1 if digest[4] % 2 else -1
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]


def similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def classify(description: str) -> str:
    words = set(re.findall(r"[a-z]+", description.lower()))
    for name, terms in [("debug", {"fix", "bug", "failure", "error", "broken"}),
                        ("refactor", {"refactor", "migrate", "migration"}),
                        ("test", {"test", "tests", "coverage"})]:
        if words & terms:
            return name
    return "build"


def utility(success: float, seconds: float, calls: float, tokens: float, risk: float = 0,
            uncertainty: float = 0, reversibility: float = 1) -> float:
    return (0.55 * success - 0.12 * min(seconds / 900, 1) - 0.10 * min(calls / 40, 1)
            - 0.08 * min(tokens / 16000, 1) - 0.08 * risk - 0.04 * uncertainty
            + 0.03 * reversibility)


def marginal_cost(seconds: float, calls: float, tokens: float) -> float:
    """Utility cost of additional work, uncapped: the caps in utility() describe whole tasks, not increments."""
    return 0.12 * seconds / 900 + 0.10 * calls / 40 + 0.08 * tokens / 16000


# ------------------------------------------------------------------ Pareto efficiency


def dominates(a: CandidatePath, b: CandidatePath) -> bool:
    """a is at least as good as b on every objective and strictly better on at least one."""
    strictly = False
    for name, sign in OBJECTIVES:
        x, y = sign * getattr(a, name), sign * getattr(b, name)
        if x < y - EPSILON:
            return False
        strictly = strictly or x > y + EPSILON
    return strictly


def mark_dominated(paths: list[CandidatePath]) -> None:
    for path in paths:
        dominator = next((other for other in paths if other is not path and dominates(other, path)), None)
        path.dominated_by = dominator.strategy if dominator else None


# ------------------------------------------------------------------ execution budget


@dataclass(frozen=True)
class Budget:
    seconds: float
    tool_calls: float
    context_tokens: float
    source: str  # "estimated" from the planned path, or "limit" when a user limit is binding

    def usage(self, seconds: float, calls: float, tokens: float) -> float:
        """Fraction of the tightest budget dimension consumed."""
        return max(seconds / self.seconds, calls / self.tool_calls, tokens / self.context_tokens)


@dataclass(frozen=True)
class Limits:
    seconds: float | None = None
    tool_calls: float | None = None
    context_tokens: float | None = None

    def fits(self, path: CandidatePath) -> bool:
        return all(limit is None or value <= limit for value, limit in (
            (path.time_seconds, self.seconds), (path.tool_calls, self.tool_calls), (path.context_tokens, self.context_tokens)))

    def overrun(self, path: CandidatePath) -> float:
        return max([value / limit for value, limit in ((path.time_seconds, self.seconds), (path.tool_calls, self.tool_calls),
                                                       (path.context_tokens, self.context_tokens)) if limit] or [0.0])


def limits_from_env() -> Limits:
    """Optional user limits, e.g. OPENREFLEX_BUDGET="calls=40,minutes=20,tokens=60000"."""
    values: dict[str, float] = {}
    for part in os.environ.get("OPENREFLEX_BUDGET", "").split(","):
        key, _, raw = part.partition("=")
        try:
            number = float(raw)
        except ValueError:
            continue
        if number > 0 and key.strip().lower() in {"calls", "minutes", "tokens"}:
            values[key.strip().lower()] = number
    return Limits(seconds=values["minutes"] * 60 if "minutes" in values else None,
                  tool_calls=values.get("calls"), context_tokens=values.get("tokens"))


def budget_for(path: CandidatePath, limits: Limits = Limits()) -> Budget:
    """Headroom over the path's expected cost, wider while the estimate is uncertain; user limits cap it."""
    headroom = 1.875 + 0.625 * path.uncertainty  # 2.5x with no evidence, tightening toward ~1.9x
    estimated = (max(1200.0, headroom * path.time_seconds), max(30.0, headroom * path.tool_calls),
                 max(30000.0, 2 * path.context_tokens * (0.75 + 0.25 * path.uncertainty)))
    capped = tuple(value if limit is None else min(value, limit)
                   for value, limit in zip(estimated, (limits.seconds, limits.tool_calls, limits.context_tokens)))
    return Budget(*capped, source="limit" if capped != estimated else "estimated")


# ------------------------------------------------------------------ candidates


def candidates(task_id: str, task_class: str, experiences: list[Experience], limits: Limits = Limits()) -> list[CandidatePath]:
    """Candidate paths, best first: Pareto-efficient paths that fit the limits, ranked by utility."""
    templates = [
        ("inspect-first", ["Locate the relevant implementation with targeted search", "Inspect nearby conventions", "Make a small change and verify it"], .78, 420, 14, 5000, .15, .9),
        ("test-first", ["Reproduce the issue with a focused check", "Change the smallest failing behavior", "Run focused tests and relevant regression checks"], .85, 540, 18, 6000, .10, .95),
        ("incremental", ["Identify interfaces and a reversible first slice", "Implement and validate one slice at a time", "Check integration behavior"], .82, 660, 22, 8000, .12, .95),
    ]
    result = []
    for strategy, steps, prior, seconds, calls, tokens, risk, reversible in templates:
        if task_class == "debug" and strategy == "test-first":
            prior += .08
        if task_class == "refactor" and strategy == "incremental":
            prior += .08
        evidence = [e for e in experiences if e.strategy == strategy and e.status != "unknown"]
        n, w = len(evidence), PRIOR_WEIGHT
        probability = (prior * w + sum(e.status == "success" for e in evidence)) / (w + n)
        if n:
            seconds = (seconds * w + sum(e.elapsed_seconds for e in evidence)) / (w + n)
            calls = (calls * w + sum(e.tool_calls for e in evidence)) / (w + n)
            tokens = (tokens * w + sum(e.output_tokens_estimate for e in evidence)) / (w + n)
            # Risk: how often this path ran into a costly detour (a failure loop, stalled progress, budget overrun).
            risk = (risk * w + sum(bool(DETOUR_ALERTS & set(e.alerts)) for e in evidence)) / (w + n)
        regrets = [e.estimated_regret for e in evidence if e.estimated_regret is not None]
        expected_regret = sum(regrets) / (w + len(regrets))  # shrunk toward zero regret
        uncertainty = 1 / math.sqrt(1 + n)
        path = CandidatePath(task_id=task_id, strategy=strategy, steps=steps,
                             success_probability=probability, time_seconds=seconds, tool_calls=calls,
                             context_tokens=tokens, risk=min(risk, 1.0), uncertainty=uncertainty,
                             reversibility=reversible, expected_regret=expected_regret, evidence_count=n)
        path.score = round(utility(probability, seconds, calls, tokens, path.risk, uncertainty, reversible)
                           - REGRET_WEIGHT * expected_regret, 5)
        result.append(path)
    mark_dominated(result)
    for path in result:
        path.within_limits = limits.fits(path)
    feasible = any(p.within_limits and not p.dominated_by for p in result)
    return sorted(result, key=lambda p: (p.dominated_by is not None,
                                         not p.within_limits if feasible else limits.overrun(p) > 1,
                                         -p.score if feasible else limits.overrun(p), p.strategy))
