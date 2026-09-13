"""Simulated benchmark: baseline agent vs. the same agent guided by OpenReflex.

What this measures: whether the real engine (hook events in, contexts/alerts out) learns from noisy outcomes
fast enough to route toward better strategies, surface useful files, and cut failure loops, and how that
compounds over repeated task families.

What this does NOT measure: real-world agent gains. Every environment parameter below (strategy success
rates, call counts, how much a file hint saves, how often an agent heeds an alert) is an explicit assumption
in SIMULATION_ASSUMPTIONS. Validate claims with A/B runs on real tasks before quoting them.
"""

import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .engine import Engine
from .routing import utility
from .store import Store

SIMULATION_ASSUMPTIONS = {
    "baseline_strategy": "inspect-first 60%, otherwise uniform among the three strategies (no memory)",
    "guided_follow_rate": 0.8,
    "file_hint_search_reduction": "search/read calls drop from 6-9 to 2-3 when the context names relevant files",
    "alert_heed_rate": 0.7,
    "failure_loop": "probability per task is family-specific; an unheeded loop runs 5 extra failing attempts",
    "seconds_per_call": 25,
    "tokens_per_call": {"search": 400, "read": 1500, "edit": 300, "test": 1100},
}
STRATEGIES = ("inspect-first", "test-first", "incremental")


@dataclass(frozen=True)
class Family:
    name: str
    templates: tuple[str, ...]
    success: dict[str, float]    # true success probability per strategy
    extra_calls: dict[str, int]  # strategy-specific extra work in this area of the codebase
    loop_probability: float
    files: tuple[str, ...]


FAMILIES = (
    Family("auth-expiry", ("Fix the login bug where expired {x} tokens are accepted",
                           "Fix expired {x} token still accepted by the login check"),
           {"inspect-first": .55, "test-first": .9, "incremental": .7}, {"inspect-first": 2, "test-first": 1, "incremental": 5},
           .35, ("src/auth/session.py", "tests/test_session.py")),
    Family("webhook-signature", ("Fix failing {x} webhook signature verification",
                                 "Fix {x} webhook signature check rejecting valid payloads"),
           {"inspect-first": .8, "test-first": .6, "incremental": .65}, {"inspect-first": 0, "test-first": 6, "incremental": 4},
           .3, ("src/payments/webhooks.py",)),
    Family("billing-refactor", ("Refactor the {x} billing module into smaller services",
                                "Refactor {x} billing calculations out of the invoice controller"),
           {"inspect-first": .5, "test-first": .6, "incremental": .88}, {"inspect-first": 3, "test-first": 4, "incremental": 2},
           .2, ("src/billing/invoice.py", "src/billing/tax.py", "src/billing/service.py")),
    Family("csv-export", ("Add {x} CSV export to the reports page",
                          "Build a {x} CSV export endpoint for monthly reports"),
           {"inspect-first": .85, "test-first": .8, "incremental": .8}, {"inspect-first": 0, "test-first": 3, "incremental": 5},
           .1, ("src/reports/export.py", "src/reports/views.py")),
    Family("parser-tests", ("Increase test coverage for the {x} config parser",
                            "Add tests covering {x} edge cases in the config parser"),
           {"inspect-first": .75, "test-first": .9, "incremental": .8}, {"inspect-first": 2, "test-first": 0, "incremental": 3},
           .15, ("src/config/parser.py", "tests/test_parser.py")),
)
VARIANTS = ("admin", "mobile", "legacy", "tenant", "guest", "partner", "nightly", "api")
TOKENS = SIMULATION_ASSUMPTIONS["tokens_per_call"]


def true_utility(family: Family, strategy: str, search_calls: float = 7.5) -> float:
    calls = search_calls + 4 + family.extra_calls[strategy] + family.loop_probability * 2.5
    return utility(family.success[strategy], calls * 25, calls, calls * 800, 0.12, 0, 0.93)


def oracle(family: Family) -> str:
    return max(STRATEGIES, key=lambda s: true_utility(family, s))


class Agent:
    def __init__(self, guided: bool, rng: random.Random, engine: Engine, clock: list[float]):
        self.guided, self.rng, self.engine, self.clock = guided, rng, engine, clock
        self.calls = 0

    def tick(self, seconds: float = 25):
        self.clock[0] += seconds * self.rng.uniform(0.6, 1.4)

    def tool(self, session: str, name: str, arguments: dict, success: bool = True, error: str | None = None,
             category: str = "read") -> str | None:
        self.calls += 1
        self.tick()
        tool_id = f"{session}-{self.calls}"
        warning = self.engine.tool_start("sim", session, tool_id, name, arguments)
        self.tick(3)
        alert = self.engine.tool_end("sim", session, tool_id, name, arguments, success, error, TOKENS[category] * 4)
        return alert or warning


def episode(agent: Agent, family: Family, index: int) -> dict:
    rng, session = agent.rng, f"{family.name}-{index}"
    prompt = rng.choice(family.templates).format(x=rng.choice(VARIANTS))
    context = agent.engine.prompt("sim", session, prompt)
    engine_pick = agent.engine.store.get(agent.engine.store.latest("sim", session).recommended_path_id).strategy

    habit = "inspect-first" if rng.random() < 0.6 else rng.choice(STRATEGIES)
    strategy = engine_pick if agent.guided and rng.random() < SIMULATION_ASSUMPTIONS["guided_follow_rate"] else habit
    hinted = agent.guided and context is not None and any(f in context for f in family.files)

    start_calls, tokens = agent.calls, 0
    area = family.files[0].rsplit("/", 1)[0]
    for i in range(rng.randint(2, 3) if hinted else rng.randint(6, 9)):
        category = "search" if i % 2 == 0 else "read"
        name, args = ("Grep", {"pattern": f"{family.name}-{i}", "path": area}) if category == "search" else \
            ("Read", {"file_path": family.files[i % len(family.files)]})
        agent.tool(session, name, args, category=category)
        tokens += TOKENS[category]

    test = ("Bash", {"command": f"pytest tests -k {family.name}"})
    edit = ("Edit", {"file_path": family.files[0], "old_string": "a", "new_string": str(index)})
    succeeded = rng.random() < family.success[strategy]
    failure = f"AssertionError: {family.name} check failed"

    def run(name_args, category, success=True, error=None):
        nonlocal tokens
        tokens += TOKENS[category]
        return agent.tool(session, *name_args, success=success, error=error, category=category)

    if strategy == "test-first":
        run(test, "test", False, failure)
    for i in range(family.extra_calls[strategy]):
        run(("Read", {"file_path": family.files[i % len(family.files)], "offset": i * 50}), "read")
    slices = 3 if strategy == "incremental" else 1
    for i in range(slices):
        run(edit, "edit")
        if i < slices - 1:
            run(test, "test")

    if rng.random() < family.loop_probability:
        for attempt in range(5):
            alert = run(test, "test", False, failure)
            run(edit, "edit")
            if alert and agent.guided and rng.random() < SIMULATION_ASSUMPTIONS["alert_heed_rate"]:
                break
    run(test, "test", succeeded, None if succeeded else failure)
    agent.engine.stop("sim", session)
    agent.tick(120)

    best = oracle(family)
    return {"family": family.name, "strategy": strategy, "recommended": engine_pick, "oracle": best,
            "success": succeeded, "tool_calls": agent.calls - start_calls, "tokens": tokens,
            "seconds": (agent.calls - start_calls) * SIMULATION_ASSUMPTIONS["seconds_per_call"],
            "regret": round(true_utility(family, best) - true_utility(family, strategy), 4)}


def run_arm(guided: bool, episodes: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as directory:
        clock = [1_700_000_000.0]
        engine = Engine(Path(directory), Store(Path(directory) / "bench.sqlite3"), clock=lambda: clock[0])
        try:
            agent = Agent(guided, rng, engine, clock)
            return [episode(agent, FAMILIES[i % len(FAMILIES)] if i % 3 else rng.choice(FAMILIES), i)
                    for i in range(episodes)]
        finally:
            engine.close()


def summarize(results: list[dict]) -> dict:
    quarter = max(1, len(results) // 4)
    second_half = results[len(results) // 2:]
    return {
        "tool_calls": round(mean(r["tool_calls"] for r in results), 2),
        "tokens": round(mean(r["tokens"] for r in results), 1),
        "seconds": round(mean(r["seconds"] for r in results), 1),
        "success_rate": round(mean(r["success"] for r in results), 3),
        "regret_first_quarter": round(mean(r["regret"] for r in results[:quarter]), 4),
        "regret_last_quarter": round(mean(r["regret"] for r in results[-quarter:]), 4),
        "routing_agreement_second_half": round(mean(r["recommended"] == r["oracle"] for r in second_half), 3),
    }


def run_benchmark(episodes: int = 150, seeds: int = 3) -> dict:
    per_seed = []
    for seed in range(seeds):
        per_seed.append({"seed": seed, "baseline": summarize(run_arm(False, episodes, seed)),
                         "guided": summarize(run_arm(True, episodes, seed))})
    keys = per_seed[0]["baseline"].keys()
    baseline = {k: round(mean(s["baseline"][k] for s in per_seed), 4) for k in keys}
    guided = {k: round(mean(s["guided"][k] for s in per_seed), 4) for k in keys}

    def change(key):
        return round((guided[key] - baseline[key]) / baseline[key], 3) if baseline[key] else None

    return {
        "kind": "simulation",
        "episodes_per_arm": episodes, "seeds": seeds,
        "assumptions": SIMULATION_ASSUMPTIONS,
        "oracle_best_strategy": {f.name: oracle(f) for f in FAMILIES},
        "baseline": baseline, "guided": guided,
        "relative_change": {"tool_calls": change("tool_calls"), "tokens": change("tokens"), "time": change("seconds"),
                            "success_rate_points": round(guided["success_rate"] - baseline["success_rate"], 3)},
        "targets": {"tool_calls": -0.20, "tokens": -0.20, "time": -0.15, "routing_agreement": 0.70},
        "per_seed": per_seed,
    }


def format_report(report: dict) -> str:
    b, g, c = report["baseline"], report["guided"], report["relative_change"]
    rows = [
        ("tool calls / task", b["tool_calls"], g["tool_calls"], f"{c['tool_calls']:+.0%}", "-20..-30%"),
        ("output tokens / task", b["tokens"], g["tokens"], f"{c['tokens']:+.0%}", "-20%"),
        ("time / task (s)", b["seconds"], g["seconds"], f"{c['time']:+.0%}", "-15%"),
        ("success rate", b["success_rate"], g["success_rate"], f"{c['success_rate_points']:+.3f} pts", ">= baseline"),
        ("regret, first quarter", b["regret_first_quarter"], g["regret_first_quarter"], "", ""),
        ("regret, last quarter", b["regret_last_quarter"], g["regret_last_quarter"], "", "declining"),
        ("routing agreement (2nd half)", "-", g["routing_agreement_second_half"], "", "> 0.70"),
    ]
    lines = [f"SIMULATED benchmark - {report['episodes_per_arm']} tasks/arm x {report['seeds']} seeds "
             "(assumption-driven; not evidence of real-world gains)", ""]
    lines.append(f"{'metric':30} {'baseline':>10} {'guided':>10} {'change':>12}  target")
    def cell(value):
        return f"{value:,.3f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)

    for name, base, guide, delta, target in rows:
        lines.append(f"{name:30} {cell(base):>10} {cell(guide):>10} {delta:>12}  {target}")
    return "\n".join(lines)
