"""Controlled OpenReflex replay using real SecChecker task families and paths.

This is not a live-agent benchmark. It verifies that the OpenReflex engine can reuse
project-specific execution evidence, surface relevant SecChecker files, detect a stalled
path, recommend a pivot, and persist a reusable resolution lesson on an actual SecChecker
checkout. It deliberately does not estimate developer time or token savings.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from openreflex.engine import Engine
from openreflex.store import Store


REQUIRED = [
    "secchecker/llm_scanner.py",
    "secchecker/config.py",
    "tests/test_llm_scanner.py",
    "tests/test_config.py",
    "tests/test_severity_contract.py",
    "bench/run.py",
]


class Clock:
    def __init__(self) -> None:
        self.value = 1_700_000_000.0

    def now(self) -> float:
        return self.value

    def step(self, seconds: float = 5.0) -> None:
        self.value += seconds


def tool(engine: Engine, clock: Clock, session: str, number: int, name: str, args: dict,
         *, success: bool = True, error: str | None = None, output_chars: int = 400) -> str | None:
    tool_id = f"{session}-{number}"
    engine.tool_start("replay", session, tool_id, name, args)
    clock.step()
    return engine.tool_end("replay", session, tool_id, name, args, success, error, output_chars)


def seed_prior(engine: Engine, clock: Clock) -> None:
    session = "seed-false-positive"
    engine.prompt("replay", session,
                  "Fix LLM scanner false positive where keyword co-occurrence flags benign code")
    tool(engine, clock, session, 1, "Read", {"file_path": "secchecker/llm_scanner.py"})
    tool(engine, clock, session, 2, "Bash", {"command": "pytest tests/test_llm_scanner.py -q"},
         success=False, error="AssertionError: benign code flagged")
    tool(engine, clock, session, 3, "Edit", {"file_path": "secchecker/llm_scanner.py",
                                              "old_string": "lexical", "new_string": "dataflow"})
    tool(engine, clock, session, 4, "Bash", {"command": "pytest tests/test_llm_scanner.py -q"}, success=True)
    engine.stop("replay", session)
    clock.step(60)


def run_replay(target: Path) -> dict:
    missing = [path for path in REQUIRED if not (target / path).exists()]
    if missing:
        raise SystemExit(f"SecChecker checkout missing expected paths: {missing}")

    with tempfile.TemporaryDirectory() as directory:
        clock = Clock()
        store = Store(Path(directory) / "secchecker-replay.sqlite3")
        engine = Engine(target, store, clock=clock.now)
        try:
            seed_prior(engine, clock)

            session = "repeat-false-positive"
            prompt = "Fix LLM scanner false positive for poisoned docstring on a non-MCP function"
            context = engine.prompt("replay", session, prompt)
            execution = engine.store.latest("replay", session)
            if execution is None:
                raise AssertionError("execution was not created")
            start_snapshot = engine.decision_snapshots(execution.id)[0]
            relevant_file_reused = bool(context and "secchecker/llm_scanner.py" in context)

            engine.choose_path("inspect-first", execution_id=execution.id)
            tool(engine, clock, session, 1, "Edit", {"file_path": "tests/test_llm_scanner.py",
                                                       "old_string": "case", "new_string": "regression"})

            alert = None
            for index in range(2, 17):
                alert = tool(engine, clock, session, index, "Read",
                             {"file_path": "secchecker/llm_scanner.py", "offset": index * 20}) or alert

            pivot_recommended = bool(alert and "pivot to test-first" in alert)

            tool(engine, clock, session, 17, "Bash", {"command": "pytest tests/test_llm_scanner.py -q"},
                 success=False, error="AssertionError: poisoned docstring false positive")
            tool(engine, clock, session, 18, "Edit", {"file_path": "secchecker/llm_scanner.py",
                                                        "old_string": "docstring", "new_string": "mcp_tool_docstring"})
            tool(engine, clock, session, 19, "Bash", {"command": "pytest tests/test_llm_scanner.py -q"}, success=True)
            outcome = engine.stop("replay", session)

            lessons = engine.store.list("Lesson", limit=100)
            resolution_lessons = [lesson for lesson in lessons if lesson.kind == "resolution"]
            learned_resolution = any("poisoned docstring false positive" in lesson.text for lesson in resolution_lessons)

            follow_session = "third-false-positive"
            follow_context = engine.prompt(
                "replay", follow_session,
                "Fix another LLM scanner false positive where a benign MCP description is flagged",
            )
            resolution_reused = bool(follow_context and "resolved by an edit in secchecker/llm_scanner.py" in follow_context)

            result = {
                "kind": "controlled-repo-replay",
                "target": "vishnu-77/secchecker",
                "live_agent": False,
                "claims": {
                    "real_world_speedup": False,
                    "token_savings": False,
                    "developer_time_savings": False,
                },
                "checks": {
                    "real_repo_paths_verified": True,
                    "prior_experience_retrieved": start_snapshot.evidence_count >= 1,
                    "relevant_file_reused": relevant_file_reused,
                    "recommended_path": start_snapshot.strategy,
                    "stalled_inspect_path_detected": bool(alert and "calls" in alert),
                    "pivot_to_test_first_recommended": pivot_recommended,
                    "verified_outcome": outcome.status if outcome else None,
                    "resolution_lesson_created": learned_resolution,
                    "resolution_lesson_reused_next_task": resolution_reused,
                },
            }

            required_true = [
                "real_repo_paths_verified",
                "prior_experience_retrieved",
                "relevant_file_reused",
                "stalled_inspect_path_detected",
                "pivot_to_test_first_recommended",
                "resolution_lesson_created",
                "resolution_lesson_reused_next_task",
            ]
            failures = [name for name in required_true if result["checks"].get(name) is not True]
            if result["checks"]["verified_outcome"] != "success":
                failures.append("verified_outcome")
            if failures:
                raise AssertionError(f"SecChecker replay failed checks: {failures}\n{json.dumps(result, indent=2)}")
            return result
        finally:
            engine.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run_replay(args.target.resolve())
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
