"""Paired real-Claude A/B evaluation for OpenReflex cold-start project memory.

The corpus is versioned under ``evals/cold_start``. Each task is read-only and has one reviewed
target file. For every task and repetition, the harness runs fresh copies of the exact same pinned
repository commit in two conditions: plain Claude Code (baseline), and Claude Code with a freshly
primed OpenReflex Project Map but no prior Experience (primed).

Arm order is deterministically shuffled within each pair to reduce temporal/provider-order bias.
The harness records real model usage, cost, tool calls, wall time, correctness, and whether the
OpenReflex context actually reached Claude. CI gates experiment validity, not a desired positive
result: a treatment that uses more tokens is still valid data.

Example:
    python scripts/live_cold_start_eval.py --seed /path/to/pinned/repo --reps 3
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "openreflex"

DEFAULT_MANIFEST = REPO / "evals" / "cold_start" / "click.json"


def _load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported eval schema: {data.get('schema_version')}")
    repo = data.get("repository") or {}
    tasks = data.get("tasks") or []
    if not repo.get("commit") or not repo.get("url") or not tasks:
        raise ValueError("manifest must define repository.url, repository.commit and tasks")
    names = set()
    for task in tasks:
        for field in ("name", "prompt", "target"):
            if not str(task.get(field) or "").strip():
                raise ValueError(f"task missing {field}: {task}")
        if task["name"] in names:
            raise ValueError(f"duplicate task name: {task['name']}")
        names.add(task["name"])
    return data


def _git_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _usage_tokens(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    values = [usage.get(key) for key in keys]
    numeric = [int(value) for value in values if isinstance(value, (int, float))]
    return sum(numeric) if numeric else None

READ_LIKE = {"Read", "Grep", "Glob"}


def find_claude() -> str:
    found = shutil.which("claude")
    if found and os.name == "nt":
        native = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if native.exists():
            return str(native)
    if not found:
        raise SystemExit("claude CLI not found on PATH")
    return found


class Harness:
    def __init__(self, model: str, root: Path):
        self.model = model
        self.root = root
        self.claude = find_claude()
        self.exe = shutil.which("openreflex")
        if not self.exe:
            raise SystemExit("openreflex is not installed in this environment")
        scripts = str(Path(self.exe).parent)
        self.base_env = {k: v for k, v in os.environ.items()
                          if k not in {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR", "PYTHONPATH"}
                          and not k.startswith("OPENREFLEX_")}
        self.base_env["PATH"] = scripts + os.pathsep + os.environ.get("PATH", "")

    def env_for(self, home: Path) -> dict:
        env = dict(self.base_env)
        env["OPENREFLEX_HOME"] = str(home)
        return env

    def cli(self, *args, cwd: Path, env: dict) -> str:
        result = subprocess.run([self.exe, *args], cwd=cwd, env=env, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f"openreflex {args} failed: {result.stderr.decode(errors='replace')}")
        return result.stdout.decode(errors="replace")

    def claude_run(self, repo: Path, prompt: str, env: dict, plugin: bool, turns: int = 20) -> dict:
        command = [self.claude, "-p", prompt, "--model", self.model, "--output-format", "stream-json", "--verbose",
                   "--permission-mode", "acceptEdits", "--max-turns", str(turns),
                   "--allowedTools", "Read", "Grep", "Glob"]
        if plugin:
            command[1:1] = ["--plugin-dir", str(PLUGIN)]
        started = time.time()
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, timeout=600)
        stream = result.stdout.decode("utf-8", errors="replace")
        events = [json.loads(line) for line in stream.splitlines() if line.startswith("{")]
        final = next((e for e in reversed(events) if e.get("type") == "result"), {})
        return {"events": events, "result": final, "seconds": round(time.time() - started, 1),
                "stderr": result.stderr.decode("utf-8", errors="replace")[-2000:], "code": result.returncode}

    def delivered_openreflex_context(self, run: dict) -> list[str]:
        """<config dir> defaults to ~/.claude but follows CLAUDE_CONFIG_DIR - this matters when this
        harness runs inside a Claude Code session using a custom profile, or the child inherits one."""
        config_dir = Path(self.base_env["CLAUDE_CONFIG_DIR"]) if self.base_env.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"
        session = run["result"].get("session_id") or next(
            (e.get("session_id") for e in run["events"] if e.get("session_id")), None)
        texts = []
        for transcript in (config_dir / "projects").glob(f"*/{session}.jsonl") if session else []:
            for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
                record = json.loads(line) if line.startswith("{") else {}
                attachment = record.get("attachment") or {}
                if attachment.get("type") == "hook_additional_context":
                    texts += [c for c in attachment.get("content", []) if isinstance(c, str)]
        return texts


def _tool_calls(run: dict) -> list[dict]:
    return [block for event in run["events"] if event.get("type") == "assistant"
            for block in event.get("message", {}).get("content", []) if block.get("type") == "tool_use"]


def _first_correct_read_index(calls: list[dict], target: str) -> int | None:
    for index, call in enumerate(calls):
        arguments = call.get("input", {})
        haystack = " ".join(str(v) for v in arguments.values())
        if target in haystack.replace("\\", "/"):
            return index
    return None


def _target_rank(delivered: list[str], target: str) -> int | None:
    for text in delivered:
        for line in text.splitlines():
            if line.startswith("Likely project locations:"):
                paths = [p.strip().rstrip(".") for p in line.split(":", 1)[1].split(",")]
                if target in paths:
                    return paths.index(target) + 1
    return None


def run_condition(harness: Harness, seed: Path, task: dict, condition: str, work: Path, rep: int) -> dict:
    repo = work / f"{task['name']}-{condition}-{rep}-repo"
    home = work / f"{task['name']}-{condition}-{rep}-home"
    shutil.copytree(seed, repo, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=eval@test", "-c", "user.name=eval", "commit", "-qm", "seed"],
                   cwd=repo, check=True)
    env = harness.env_for(home)

    primed = condition == "primed"
    if primed:
        harness.cli("approve", "--project", str(repo), cwd=repo, env=env)
        sys.path.insert(0, str(REPO / "src"))
        os.environ["OPENREFLEX_HOME"] = str(home)
        from openreflex.project_map import enrich_snapshot
        from openreflex.project_memory import build_snapshot
        snapshot = build_snapshot(repo)
        enrich_snapshot(repo)
        tracked_files = snapshot.get("project_map", {}).get("tracked_files", len(snapshot.get("indexed_files", [])))
    else:
        tracked_files = None

    run = harness.claude_run(repo, task["prompt"], env, plugin=primed)
    calls = _tool_calls(run)
    read_like = [c for c in calls if c.get("name") in READ_LIKE]
    first_correct = _first_correct_read_index(read_like, task["target"])
    delivered = harness.delivered_openreflex_context(run) if primed else []

    report = {
        "condition": condition,
        "code": run["code"],
        "observed_model_tokens": _usage_tokens(run["result"].get("usage")),
        "seconds": run["seconds"],
        "num_turns": run["result"].get("num_turns"),
        "total_cost_usd": run["result"].get("total_cost_usd"),
        "usage": run["result"].get("usage"),
        "exploration_calls": len(read_like),
        "total_tool_calls": len(calls),
        "found_correct_file": first_correct is not None,
        "calls_to_find_correct_file": (first_correct + 1) if first_correct is not None else None,
        "answer_mentions_target": task["target"].split("/")[-1] in (run["result"].get("result") or ""),
        "openreflex_context_delivered": bool(delivered),
        "target_rank_in_context": _target_rank(delivered, task["target"]),
        "tracked_files_in_project_map": tracked_files,
        "stderr_tail": run["stderr"][-500:] if run["code"] != 0 else "",
    }
    shutil.rmtree(repo, ignore_errors=True)
    shutil.rmtree(home, ignore_errors=True)
    return report


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _paired_summary(results: list[dict], manifest: dict, model: str) -> dict:
    pairs: dict[tuple[str, int], dict[str, dict]] = {}
    for row in results:
        pairs.setdefault((row["task"], int(row["rep"])), {})[row["condition"]] = row

    valid_pairs = []
    for key, arms in sorted(pairs.items()):
        baseline, primed = arms.get("baseline"), arms.get("primed")
        if baseline and primed and baseline["code"] == 0 and primed["code"] == 0:
            valid_pairs.append((key, baseline, primed))

    def profile(condition: str) -> dict:
        rows = [row for row in results if row["condition"] == condition and row["code"] == 0]
        token_values = [row["observed_model_tokens"] for row in rows if row["observed_model_tokens"] is not None]
        return {
            "runs": len(rows),
            "success_rate": _mean([1.0 if row["found_correct_file"] and row["answer_mentions_target"] else 0.0 for row in rows]),
            "observed_model_tokens": _mean(token_values),
            "exploration_calls": _mean([row["exploration_calls"] for row in rows]),
            "total_tool_calls": _mean([row["total_tool_calls"] for row in rows]),
            "seconds": _mean([row["seconds"] for row in rows]),
            "cost_usd": _mean([row["total_cost_usd"] for row in rows]),
        }

    def paired_change(field: str) -> float | None:
        changes = []
        for _, baseline, primed in valid_pairs:
            before, after = baseline.get(field), primed.get(field)
            if isinstance(before, (int, float)) and before > 0 and isinstance(after, (int, float)):
                changes.append((after - before) / before)
        return round(sum(changes) / len(changes), 4) if changes else None

    missing_context = [
        {"task": row["task"], "rep": row["rep"]}
        for row in results
        if row["condition"] == "primed" and row["code"] == 0 and not row["openreflex_context_delivered"]
    ]
    return {
        "kind": "real-agent-paired-pilot",
        "claim_scope": "pilot only; do not generalize causal token savings beyond this pinned corpus",
        "corpus": manifest["name"],
        "repository": manifest["repository"],
        "model": model,
        "claude_code_version": manifest.get("claude_code_version"),
        "tasks": len(manifest["tasks"]),
        "pairs_total": len(pairs),
        "pairs_valid": len(valid_pairs),
        "baseline": profile("baseline"),
        "primed": profile("primed"),
        "paired_relative_change": {
            "observed_model_tokens": paired_change("observed_model_tokens"),
            "exploration_calls": paired_change("exploration_calls"),
            "total_tool_calls": paired_change("total_tool_calls"),
            "seconds": paired_change("seconds"),
            "cost_usd": paired_change("total_cost_usd"),
        },
        "missing_treatment_context": missing_context,
    }


def _summarize(results: list[dict], tasks: list[dict]) -> None:
    print("\n--- summary (mean over reps) ---")
    for task in tasks:
        row = [r for r in results if r["task"] == task["name"]]
        for condition in ("baseline", "primed"):
            subset = [r for r in row if r["condition"] == condition]
            print(f"{task['name']:20s} {condition:9s} n={len(subset)} "
                  f"exploration_calls={_mean([r['exploration_calls'] for r in subset])} "
                  f"calls_to_find={_mean([r['calls_to_find_correct_file'] for r in subset])} "
                  f"found_rate={_mean([1.0 if r['found_correct_file'] else 0.0 for r in subset])} "
                  f"seconds={_mean([r['seconds'] for r in subset])} "
                  f"cost=${_mean([r['total_cost_usd'] for r in subset])}")
    total_cost = sum(r["total_cost_usd"] or 0 for r in results)
    print(f"\ntotal cost: ${round(total_cost, 4)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, help="Path to the exact pinned checkout named by the manifest")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--model", default="", help="Override the manifest model")
    parser.add_argument("--reps", type=int, default=3, help="Paired repetitions per task")
    parser.add_argument("--order-seed", type=int, default=20260922)
    parser.add_argument("--out", default="cold-start-eval-results.json")
    parser.add_argument("--summary-out", default="cold-start-eval-summary.json")
    args = parser.parse_args()

    manifest = _load_manifest(Path(args.manifest))
    seed = Path(args.seed).resolve()
    if not seed.is_dir():
        raise SystemExit(f"seed repo not found: {seed}")
    actual_sha = _git_sha(seed)
    expected_sha = manifest["repository"]["commit"]
    if actual_sha != expected_sha:
        raise SystemExit(f"seed commit mismatch: expected {expected_sha}, got {actual_sha}")
    missing_targets = [task["target"] for task in manifest["tasks"] if not (seed / task["target"]).is_file()]
    if missing_targets:
        raise SystemExit("manifest target files missing from pinned repository: " + ", ".join(missing_targets))

    model = args.model or manifest.get("model") or "sonnet"
    work = Path(tempfile.mkdtemp(prefix="openreflex-coldstart-"))
    harness = Harness(model, work)
    print(
        f"corpus: {manifest['name']}\nseed: {seed}\ncommit: {actual_sha}\n"
        f"workdir: {work}\nclaude: {harness.claude}\nopenreflex: {harness.exe}\n"
        f"model: {model}\nreps: {args.reps}\n"
    )

    results = []
    try:
        for task in manifest["tasks"]:
            for rep in range(1, args.reps + 1):
                conditions = ["baseline", "primed"]
                random.Random(f"{args.order_seed}:{task['name']}:{rep}").shuffle(conditions)
                for condition in conditions:
                    print(f"running {task['name']} / {condition} / rep {rep} ...")
                    report = run_condition(harness, seed, task, condition, work, rep)
                    report["task"] = task["name"]
                    report["rep"] = rep
                    report["target"] = task["target"]
                    results.append(report)
                    print(
                        f"  [{('ok' if report['code'] == 0 else 'FAIL')}] "
                        f"{report['exploration_calls']} exploration calls, "
                        f"tokens={report['observed_model_tokens']}, "
                        f"found target: {report['found_correct_file']}, "
                        f"rank: {report['target_rank_in_context']}, "
                        f"{report['seconds']}s, cost ${report['total_cost_usd']}"
                    )

        summary = _paired_summary(results, manifest, model)
        Path(args.out).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        Path(args.summary_out).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {args.out} and {args.summary_out}")
        _summarize(results, manifest["tasks"])
        print("\n--- paired result ---")
        print(json.dumps(summary, indent=2))

        # Gate experiment validity, not a desired positive result. Negative efficacy results are data.
        if summary["pairs_valid"] == 0:
            print("No valid baseline/treatment pairs completed.", file=sys.stderr)
            return 2
        if summary["missing_treatment_context"]:
            print("OpenReflex treatment ran without delivered project context.", file=sys.stderr)
            return 2
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
