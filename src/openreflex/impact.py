"""Opt-in token-efficiency and environmental equivalence metrics.

This module is deliberately isolated from OpenReflex's capture/runtime path. Importing it does not initialise
EcoLogits, patch provider clients, write to the Experience Graph, or make network calls. Project-level token
savings are observational counterfactuals: a benefited execution is compared only with earlier successful
executions of the same task class that did not receive prior experience.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from statistics import median
from typing import Iterable

EPA_TREE_KG_CO2_PER_YEAR = 60.0


@dataclass(frozen=True)
class EfficiencyComparison:
    task_class: str
    actual_tokens: int
    baseline_tokens: int
    token_delta: int
    actual_tool_calls: int
    baseline_tool_calls: float
    tool_call_delta: float
    actual_seconds: float
    baseline_seconds: float
    seconds_delta: float
    baseline_samples: int


@dataclass(frozen=True)
class EnvironmentalImpact:
    energy_kwh: float | None
    co2e_kg: float | None
    tree_days: float | None
    methodology: str


def tree_days_from_co2e(co2e_kg: float) -> float:
    """Convert kgCO2e into EPA urban-tree sequestration-equivalent days.

    This is a communication equivalence, not a claim that trees were planted, protected, or physically saved.
    """
    if co2e_kg < 0:
        raise ValueError("co2e_kg must be non-negative")
    return co2e_kg * 365.0 / EPA_TREE_KG_CO2_PER_YEAR


def _successful_baseline(experience) -> bool:
    return (
        experience.status == "success"
        and not experience.benefited
        and experience.output_tokens_estimate > 0
    )


def build_comparisons(experiences: Iterable) -> list[EfficiencyComparison]:
    """Build conservative observational comparisons from existing Experience nodes.

    A benefited run can only use *earlier* successful, non-benefited runs of the same task class as its baseline.
    This avoids future-data leakage and never invents a baseline when none exists.
    """
    baseline_by_class: dict[str, list] = defaultdict(list)
    comparisons: list[EfficiencyComparison] = []

    for experience in sorted(experiences, key=lambda item: item.created_at):
        if _successful_baseline(experience):
            baseline_by_class[experience.task_class].append(experience)
            continue
        if experience.status != "success" or not experience.benefited or experience.output_tokens_estimate <= 0:
            continue

        baselines = baseline_by_class.get(experience.task_class, [])
        if not baselines:
            continue

        baseline_tokens = int(round(median(x.output_tokens_estimate for x in baselines)))
        baseline_calls = float(median(x.tool_calls for x in baselines))
        baseline_seconds = float(median(x.elapsed_seconds for x in baselines))
        comparisons.append(
            EfficiencyComparison(
                task_class=experience.task_class,
                actual_tokens=experience.output_tokens_estimate,
                baseline_tokens=baseline_tokens,
                token_delta=baseline_tokens - experience.output_tokens_estimate,
                actual_tool_calls=experience.tool_calls,
                baseline_tool_calls=baseline_calls,
                tool_call_delta=baseline_calls - experience.tool_calls,
                actual_seconds=experience.elapsed_seconds,
                baseline_seconds=baseline_seconds,
                seconds_delta=baseline_seconds - experience.elapsed_seconds,
                baseline_samples=len(baselines),
            )
        )

    return comparisons


def _confidence(comparisons: list[EfficiencyComparison]) -> str:
    if not comparisons:
        return "unavailable"
    # Observational matching can never be HIGH confidence; controlled benchmark/replay is required for that.
    if len(comparisons) >= 3 and min(item.baseline_samples for item in comparisons) >= 3:
        return "medium"
    return "low"


def project_impact(engine, *, co2e_kg: float | None = None) -> dict:
    """Compute additive impact metrics without mutating the engine or store."""
    experiences = engine.store.list("Experience", limit=100_000)
    comparisons = build_comparisons(experiences)

    total_tokens = sum(max(0, x.output_tokens_estimate) for x in experiences)
    baseline_tokens = sum(x.baseline_tokens for x in comparisons)
    compared_tokens = sum(x.actual_tokens for x in comparisons)
    net_token_delta = baseline_tokens - compared_tokens

    baseline_calls = sum(x.baseline_tool_calls for x in comparisons)
    actual_calls = sum(x.actual_tool_calls for x in comparisons)
    baseline_seconds = sum(x.baseline_seconds for x in comparisons)
    actual_seconds = sum(x.actual_seconds for x in comparisons)

    environmental = None
    if co2e_kg is not None:
        if co2e_kg < 0:
            raise ValueError("co2e_kg must be non-negative")
        environmental = asdict(
            EnvironmentalImpact(
                energy_kwh=None,
                co2e_kg=co2e_kg,
                tree_days=tree_days_from_co2e(co2e_kg),
                methodology="supplied CO2e estimate + EPA 60 kg CO2/tree/year equivalence",
            )
        )

    return {
        "measurement": {
            "executions": len(experiences),
            "output_tokens_estimate": total_tokens,
            "source": "existing OpenReflex output token estimates",
        },
        "counterfactual": {
            "compared_executions": len(comparisons),
            "baseline_output_tokens": baseline_tokens or None,
            "actual_output_tokens": compared_tokens or None,
            "net_token_delta": net_token_delta if comparisons else None,
            "tokens_avoided": max(0, net_token_delta) if comparisons else None,
            "extra_tokens": max(0, -net_token_delta) if comparisons else None,
            "reduction_ratio": round(net_token_delta / baseline_tokens, 4) if baseline_tokens else None,
            "tool_calls_avoided": round(baseline_calls - actual_calls, 2) if comparisons else None,
            "seconds_avoided": round(baseline_seconds - actual_seconds, 2) if comparisons else None,
            "confidence": _confidence(comparisons),
            "basis": "earlier successful same-task-class executions without prior experience; observational",
        },
        "environmental": environmental,
        "comparisons": [asdict(item) for item in comparisons],
    }


def _metric_mean(metric) -> float | None:
    if metric is None:
        return None
    value = getattr(metric, "value", None)
    if value is None:
        return None
    mean_value = getattr(value, "mean", None)
    candidate = mean_value if mean_value is not None else value
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def estimate_request_impact(
    *,
    provider: str,
    model: str,
    output_tokens: int,
    request_latency: float,
    electricity_mix_zone: str | None = None,
) -> EnvironmentalImpact:
    """Estimate one LLM request with EcoLogits when the optional dependency is installed.

    This function is intentionally request-scoped. Project task duration is not substituted for model request
    latency because tool execution and agent think time would make that environmental estimate misleading.
    """
    if output_tokens < 0 or request_latency < 0:
        raise ValueError("output_tokens and request_latency must be non-negative")
    try:
        from ecologits.tracers.utils import llm_impacts
    except ImportError as exc:
        raise RuntimeError(
            "EcoLogits is optional. Install OpenReflex with the `impact` extra to estimate request impacts."
        ) from exc

    impacts = llm_impacts(
        provider=provider,
        model_name=model,
        output_token_count=output_tokens,
        request_latency=request_latency,
        electricity_mix_zone=electricity_mix_zone,
    )
    energy = _metric_mean(getattr(impacts, "energy", None))
    co2e = _metric_mean(getattr(impacts, "gwp", None))
    return EnvironmentalImpact(
        energy_kwh=energy,
        co2e_kg=co2e,
        tree_days=tree_days_from_co2e(co2e) if co2e is not None else None,
        methodology="EcoLogits request estimate + EPA 60 kg CO2/tree/year equivalence",
    )


def _format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{digits}f}"


def format_report(data: dict) -> str:
    measurement = data["measurement"]
    counterfactual = data["counterfactual"]
    lines = [
        "OPENREFLEX / IMPACT",
        "",
        f"  executions              {_format_number(measurement['executions'])}",
        f"  output tokens observed  {_format_number(measurement['output_tokens_estimate'])}",
        f"  compared executions     {_format_number(counterfactual['compared_executions'])}",
        f"  tokens avoided          {_format_number(counterfactual['tokens_avoided'])}",
        f"  reduction               "
        + (f"{counterfactual['reduction_ratio'] * 100:.1f}%" if counterfactual["reduction_ratio"] is not None else "unavailable"),
        f"  tool calls avoided      {_format_number(counterfactual['tool_calls_avoided'])}",
        f"  execution seconds saved {_format_number(counterfactual['seconds_avoided'])}",
        f"  confidence              {counterfactual['confidence'].upper()}",
    ]
    if counterfactual["extra_tokens"]:
        lines.append(f"  extra tokens             {_format_number(counterfactual['extra_tokens'])}")
    environmental = data.get("environmental")
    if environmental:
        lines.extend(
            [
                "",
                "  ENVIRONMENTAL EQUIVALENCE",
                f"  supplied CO2e           {_format_number(environmental['co2e_kg'], 6)} kg",
                f"  tree equivalent         {_format_number(environmental['tree_days'], 4)} tree-days",
                "  estimate only; not a carbon offset or claim that trees were physically saved",
            ]
        )
    lines.extend(["", f"  basis: {counterfactual['basis']}"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openreflex-impact",
        description="Opt-in OpenReflex token-efficiency and environmental-equivalence report.",
    )
    parser.add_argument("--project")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--co2e-kg",
        type=float,
        help="Optional external CO2e estimate to convert to an EPA tree-day equivalence.",
    )
    args = parser.parse_args(argv)

    from .engine import Engine
    from .project import project_root

    project = project_root(args.project)
    engine = Engine(project)
    try:
        data = project_impact(engine, co2e_kg=args.co2e_kg)
    finally:
        engine.close()
    print(json.dumps(data, indent=2) if args.json else format_report(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
