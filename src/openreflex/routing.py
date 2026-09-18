"""Path planning from a versioned execution policy."""

import hashlib
import math
import os
import re
from dataclasses import dataclass

from .models import CandidatePath, Experience
from .policy import Policy, load_policy

OBJECTIVES = (("success_probability", 1), ("time_seconds", -1), ("tool_calls", -1), ("context_tokens", -1),
              ("risk", -1), ("uncertainty", -1), ("reversibility", 1), ("expected_regret", -1))


def _policy(policy: Policy | None) -> Policy:
    return policy or load_policy()


def embed(text: str, dimensions: int = 256) -> list[float]:
    """Offline lexical feature hashing, not a pretrained semantic model. Dimension is embedding-format v1."""
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
    for name, terms in [
        ("debug", {"fix", "bug", "failure", "error", "broken"}),
        ("refactor", {"refactor", "migrate", "migration"}),
        ("test", {"test", "tests", "coverage"}),
        ("investigate", {"research", "investigate", "investigation", "architecture", "overview", "understand",
                         "understanding", "explain", "review", "audit", "inspect", "trace", "inventory", "map"}),
        ("think", {"decide", "decision", "compare", "choose", "plan", "brainstorm", "reason", "evaluate",
                   "assess", "recommend", "strategy", "ideate"}),
    ]:
        if words & terms:
            return name
    return "build"


def task_mode(task_class: str) -> str:
    if task_class == "investigate":
        return "investigate"
    if task_class == "think":
        return "think"
    return "build"


def utility(success: float, seconds: float, calls: float, tokens: float, risk: float = 0,
            uncertainty: float = 0, reversibility: float = 1, policy: Policy | None = None) -> float:
    cfg = _policy(policy)
    weights = cfg.table("routing.utility")
    norm = cfg.table("routing.normalization")
    return (float(weights["success"]) * success
            - float(weights["time"]) * min(seconds / float(norm["time_seconds"]), 1)
            - float(weights["tool_calls"]) * min(calls / float(norm["tool_calls"]), 1)
            - float(weights["context_tokens"]) * min(tokens / float(norm["context_tokens"]), 1)
            - float(weights["risk"]) * risk
            - float(weights["uncertainty"]) * uncertainty
            + float(weights["reversibility"]) * reversibility)


def marginal_cost(seconds: float, calls: float, tokens: float, policy: Policy | None = None) -> float:
    cfg = _policy(policy)
    weights = cfg.table("routing.utility")
    norm = cfg.table("routing.normalization")
    return (float(weights["time"]) * seconds / float(norm["time_seconds"])
            + float(weights["tool_calls"]) * calls / float(norm["tool_calls"])
            + float(weights["context_tokens"]) * tokens / float(norm["context_tokens"]))


def dominates(a: CandidatePath, b: CandidatePath, policy: Policy | None = None) -> bool:
    cfg = _policy(policy)
    strictly = False
    epsilon = cfg.number("routing.epsilon")
    for name, sign in OBJECTIVES:
        x, y = sign * getattr(a, name), sign * getattr(b, name)
        if x < y - epsilon:
            return False
        strictly = strictly or x > y + epsilon
    return strictly


def mark_dominated(paths: list[CandidatePath], policy: Policy | None = None) -> None:
    cfg = _policy(policy)
    for path in paths:
        dominator = next((other for other in paths if other is not path and dominates(other, path, cfg)), None)
        path.dominated_by = dominator.strategy if dominator else None


@dataclass(frozen=True)
class Budget:
    seconds: float
    tool_calls: float
    context_tokens: float
    source: str

    def usage(self, seconds: float, calls: float, tokens: float) -> float:
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


def budget_for(path: CandidatePath, limits: Limits = Limits(), policy: Policy | None = None) -> Budget:
    cfg = _policy(policy)
    values = cfg.table("routing.budget")
    uncertainty = path.uncertainty
    headroom = float(values["headroom_base"]) + float(values["headroom_uncertainty"]) * uncertainty
    estimated = (
        max(float(values["minimum_seconds"]), headroom * path.time_seconds),
        max(float(values["minimum_tool_calls"]), headroom * path.tool_calls),
        max(float(values["minimum_context_tokens"]),
            float(values["context_multiplier"]) * path.context_tokens
            * (float(values["context_base"]) + float(values["context_uncertainty"]) * uncertainty)),
    )
    capped = tuple(value if limit is None else min(value, limit)
                   for value, limit in zip(estimated, (limits.seconds, limits.tool_calls, limits.context_tokens)))
    return Budget(*capped, source="limit" if capped != estimated else "estimated")


def candidates(task_id: str, task_class: str, experiences: list[Experience], limits: Limits = Limits(),
               policy: Policy | None = None, task_mode_name: str | None = None) -> list[CandidatePath]:
    cfg = _policy(policy)
    result = []
    prior_weight = cfg.number("routing.prior_weight")
    regret_weight = cfg.number("routing.regret_weight")
    detour_alerts = set(cfg.strings("routing.alerts.detour"))
    adjustment = cfg.data.get("routing", {}).get("task_adjustments", {}).get(task_class, {})
    mode = task_mode_name or task_mode(task_class)

    for template in cfg.tables("routing.strategies"):
        modes = [str(item) for item in template.get("modes", ["build"])]
        if mode not in modes:
            continue
        strategy = str(template["name"])
        steps = [str(item) for item in template["steps"]]
        prior = float(template["prior_success"])
        seconds = float(template["time_seconds"])
        calls = float(template["tool_calls"])
        tokens = float(template["context_tokens"])
        risk = float(template["risk"])
        reversible = float(template["reversibility"])
        if adjustment and adjustment.get("strategy") == strategy:
            prior += float(adjustment.get("success_bonus", 0.0))

        evidence = [e for e in experiences if e.strategy == strategy and e.status != "unknown"]
        n = len(evidence)
        probability = (prior * prior_weight + sum(e.status == "success" for e in evidence)) / (prior_weight + n)
        if n:
            seconds = (seconds * prior_weight + sum(e.elapsed_seconds for e in evidence)) / (prior_weight + n)
            calls = (calls * prior_weight + sum(e.tool_calls for e in evidence)) / (prior_weight + n)
            tokens = (tokens * prior_weight + sum(e.output_tokens_estimate for e in evidence)) / (prior_weight + n)
            risk = (risk * prior_weight + sum(bool(detour_alerts & set(e.alerts)) for e in evidence)) / (prior_weight + n)
        regrets = [e.estimated_regret for e in evidence if e.estimated_regret is not None]
        expected_regret = sum(regrets) / (prior_weight + len(regrets))
        uncertainty = 1 / math.sqrt(1 + n)
        path = CandidatePath(task_id=task_id, strategy=strategy, steps=steps,
                             success_probability=probability, time_seconds=seconds, tool_calls=calls,
                             context_tokens=tokens, risk=min(risk, 1.0), uncertainty=uncertainty,
                             reversibility=reversible, expected_regret=expected_regret, evidence_count=n)
        path.score = round(utility(probability, seconds, calls, tokens, path.risk, uncertainty, reversible, cfg)
                           - regret_weight * expected_regret, 5)
        result.append(path)

    mark_dominated(result, cfg)
    for path in result:
        path.within_limits = limits.fits(path)
    feasible = any(p.within_limits and not p.dominated_by for p in result)
    return sorted(result, key=lambda p: (p.dominated_by is not None,
                                         not p.within_limits if feasible else limits.overrun(p) > 1,
                                         -p.score if feasible else limits.overrun(p), p.strategy))
