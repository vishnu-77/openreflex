"""Live cold-start A/B pilot: does OpenReflex's Project Map actually reduce exploration cost
on a real, unfamiliar repository's first task, compared to a plain Claude Code session?

Each task is investigation-only (Read/Grep/Glob, no edits) with one known-correct target file,
mirroring scripts/benchmark_cold_start.py's scenario shape but run against a real repo with a
real model instead of the deterministic retrieval contract alone. "Primed" means the Project Map
snapshot is built (as the background primer would do) before the session starts; "baseline" is a
plain claude session with no OpenReflex plugin/hooks at all. Both conditions get a fresh repo copy
and a fresh, empty OPENREFLEX_HOME so neither run carries over prior Experience.

Requires: `claude` (Claude Code, signed in) and openreflex installed in this Python environment.
Uses real model calls - a full pilot run costs a small amount.

    python scripts/live_cold_start_eval.py --seed /path/to/cloned/target/repo [--model haiku] [--out results.json]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "openreflex"

TASKS = [
    {
        "name": "shell-completion",
        "prompt": "Without editing any files, investigate how click implements shell completion for "
                  "command groups with subcommands. Reply with the single file path (relative to the "
                  "repo root) that contains that implementation, and a one-sentence summary.",
        "target": "src/click/shell_completion.py",
    },
    {
        "name": "type-conversion",
        "prompt": "Without editing any files, investigate where click validates and converts a Choice "
                  "option's raw string value using its type system. Reply with the single file path "
                  "(relative to the repo root) that contains that implementation, and a one-sentence summary.",
        "target": "src/click/types.py",
    },
    {
        "name": "terminal-width",
        "prompt": "Without editing any files, investigate how click determines the terminal width used "
                  "when wrapping help text. Reply with the single file path (relative to the repo root) "
                  "that contains that implementation, and a one-sentence summary.",
        "target": "src/click/formatting.py",
    },
]

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


def _summarize(results: list[dict]) -> None:
    print("\n--- summary (mean over reps) ---")
    for task in TASKS:
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
    parser.add_argument("--seed", required=True, help="Path to a local clone of the target repo")
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--reps", type=int, default=1, help="Repetitions per task/condition, to average out model variance")
    parser.add_argument("--out", default="cold-start-eval-results.json")
    args = parser.parse_args()

    seed = Path(args.seed).resolve()
    if not seed.is_dir():
        raise SystemExit(f"seed repo not found: {seed}")

    work = Path(tempfile.mkdtemp(prefix="openreflex-coldstart-"))
    harness = Harness(args.model, work)
    print(f"seed: {seed}\nworkdir: {work}\nclaude: {harness.claude}\nopenreflex: {harness.exe}\nreps: {args.reps}\n")

    results = []
    for task in TASKS:
        for condition in ("baseline", "primed"):
            for rep in range(1, args.reps + 1):
                print(f"running {task['name']} / {condition} / rep {rep} ...")
                report = run_condition(harness, seed, task, condition, work, rep)
                report["task"] = task["name"]
                report["rep"] = rep
                results.append(report)
                print(f"  [{('ok' if report['code'] == 0 else 'FAIL')}] "
                      f"{report['exploration_calls']} exploration calls, "
                      f"found target: {report['found_correct_file']}, "
                      f"rank: {report['target_rank_in_context']}, "
                      f"{report['seconds']}s, cost ${report['total_cost_usd']}")

    Path(args.out).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {args.out}")
    _summarize(results)
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
