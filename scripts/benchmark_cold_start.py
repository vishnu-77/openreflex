"""Deterministic cold-start localisation benchmark for OpenReflex Project Map.

This is intentionally model-free. It measures whether repository-derived memory can
surface known target files for representative first-run tasks while respecting the
compact context budget. It does not claim end-to-end agent success or causal token
savings; those require live-agent evaluation.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

from openreflex.project_map import enrich_snapshot
from openreflex.project_memory import build_snapshot
from openreflex.reflex_index import context_for_task


SCENARIOS = (
    ("Change payments replica count values", "charts/payments/values.yaml"),
    ("Fix payments deployment imagePullSecrets rendering", "charts/payments/templates/deployment.yaml"),
    ("Fix expired token validator in API", "services/api/token_validator.py"),
    ("Update worker retry job logic", "services/worker/jobs/retry.py"),
)


def _fixture(root: Path) -> None:
    chart = root / "charts" / "payments"
    (chart / "templates").mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: payments\ndependencies:\n  - name: redis\n    version: 20.0.0\n",
        encoding="utf-8",
    )
    (chart / "values.yaml").write_text("replicaCount: 2\nimagePullSecrets: []\n", encoding="utf-8")
    (chart / "templates" / "deployment.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: payments\n",
        encoding="utf-8",
    )
    (chart / "templates" / "service.yaml").write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: payments\n",
        encoding="utf-8",
    )

    api = root / "services" / "api"
    api.mkdir(parents=True)
    (api / "package.json").write_text(json.dumps({"dependencies": {"zod": "4"}}), encoding="utf-8")
    (api / "token_validator.py").write_text(
        "def validate_expired_token(token):\n    return bool(token)\n", encoding="utf-8"
    )
    (api / "router.py").write_text("def route_request():\n    return True\n", encoding="utf-8")

    worker = root / "services" / "worker"
    (worker / "jobs").mkdir(parents=True)
    (worker / "pyproject.toml").write_text(
        "[project]\nname='worker'\ndependencies=['pydantic>=2']\n", encoding="utf-8"
    )
    (worker / "jobs" / "retry.py").write_text(
        "def retry_job(attempt):\n    return attempt < 3\n", encoding="utf-8"
    )

    decoys = root / "internal" / "generated"
    decoys.mkdir(parents=True)
    for index in range(30):
        (decoys / f"helper_{index}.py").write_text(
            f"def helper_{index}():\n    return {index}\n", encoding="utf-8"
        )


def _locations(context: str) -> list[str]:
    prefix = "Likely project locations: "
    for line in context.splitlines():
        if line.startswith(prefix):
            payload = line[len(prefix):].rstrip(".")
            return [item.strip() for item in payload.split(",") if item.strip()]
    return []


def run(out: Path) -> dict:
    rows = []
    with tempfile.TemporaryDirectory(prefix="openreflex-cold-start-") as temp:
        project = Path(temp)
        _fixture(project)
        build_snapshot(project)
        snapshot = enrich_snapshot(project)

        for prompt, target in SCENARIOS:
            context = context_for_task(project, prompt) or ""
            locations = _locations(context)
            rows.append(
                {
                    "prompt": prompt,
                    "target": target,
                    "target_hit": target in locations,
                    "rank": locations.index(target) + 1 if target in locations else None,
                    "retrieved_files": len(locations),
                    "context_chars": len(context),
                    "structural_evidence_labelled": "structural priors" in context,
                }
            )

        dependencies = {
            (item.get("name"), item.get("source")) for item in snapshot.get("project_map", {}).get("dependencies", [])
        }

    hit_rate = sum(row["target_hit"] for row in rows) / len(rows)
    result = {
        "benchmark": "project-map-cold-start-v1",
        "scenarios": len(rows),
        "target_file_hit_rate": round(hit_rate, 3),
        "median_target_rank": statistics.median(row["rank"] for row in rows if row["rank"] is not None),
        "mean_retrieved_files": round(statistics.mean(row["retrieved_files"] for row in rows), 2),
        "mean_context_chars": round(statistics.mean(row["context_chars"] for row in rows), 2),
        "max_context_chars": max(row["context_chars"] for row in rows),
        "all_structural_evidence_labelled": all(row["structural_evidence_labelled"] for row in rows),
        "nested_manifest_evidence": {
            "helm": ("redis", "charts/payments/Chart.yaml") in dependencies,
            "node": ("zod", "services/api/package.json") in dependencies,
            "python": ("pydantic", "services/worker/pyproject.toml") in dependencies,
        },
        "rows": rows,
        "scope_note": (
            "Model-free localisation benchmark only; does not establish end-to-end success, causal token savings, "
            "or time savings."
        ),
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if hit_rate < 1.0:
        raise SystemExit(f"cold-start target-file hit rate regressed: {hit_rate:.3f}")
    if result["max_context_chars"] > 1800:
        raise SystemExit(f"cold-start context exceeded budget: {result['max_context_chars']}")
    if not result["all_structural_evidence_labelled"]:
        raise SystemExit("cold-start context lost structural-evidence labelling")
    if not all(result["nested_manifest_evidence"].values()):
        raise SystemExit("nested manifest evidence missing from Project Map")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("cold-start-results.json"))
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
