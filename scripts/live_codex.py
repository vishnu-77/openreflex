"""Live end-to-end tests: real `codex exec` sessions with OpenReflex installed through `openreflex install codex`.

Requires: `codex` (Codex CLI, signed in) and `openreflex` installed in the Python running this script, plus
pytest in that environment. Uses real model calls on your Codex account.

    python scripts/live_codex.py [--only capture,...] [--keep]

Every scenario runs in a throwaway git repo with an isolated OPENREFLEX_HOME and asserts on the captured
Experience Graph; delivery to the model is checked in the session rollout Codex writes to ~/.codex/sessions.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_claude_code import ALWAYS_FAILS, Harness  # noqa: E402 - shared repo fixtures and graph access

FIX_PROMPT = ("The parse_date function in dates.py returns the wrong month. First run python -m pytest -q to see "
              "the failure, then fix the bug and run the tests again.")


class CodexHarness(Harness):
    def __init__(self, keep: bool):
        super().__init__(model="", keep=keep)
        self.codex = shutil.which("codex")
        if not self.codex:
            raise SystemExit("codex CLI not found on PATH")

    def repo(self, name: str, extra: dict[str, str] | None = None) -> Path:
        path = super().repo(name, extra)
        self.cli("install", "codex", "--project", str(path), cwd=path)
        return path

    def codex_run(self, repo: Path, prompt: str) -> dict:
        # Hooks and project config only load for trusted projects; the flags keep the run non-interactive.
        trusted = f'projects."{str(repo)}".trust_level="trusted"'.replace("\\", "\\\\")
        command = [self.codex, "exec", "--json", "--dangerously-bypass-hook-trust", "--approve-for-me",
                   "-c", trusted, "-C", str(repo), prompt]
        started = time.time()
        result = subprocess.run(command, cwd=repo, env=self.env, capture_output=True, timeout=900,
                                stdin=subprocess.DEVNULL)
        stream = result.stdout.decode("utf-8", errors="replace")
        return {"events": [json.loads(line) for line in stream.splitlines() if line.startswith("{")], "raw": stream,
                "rollout": self.rollout(repo, started), "seconds": round(time.time() - started, 1),
                "stderr": result.stderr.decode("utf-8", errors="replace")[-2000:], "code": result.returncode}

    @staticmethod
    def rollout(repo: Path, since: float) -> str:
        """The rollout Codex wrote for this run: the newest top-level session whose recorded cwd is the repo.
        Approval reviews run as sub-sessions in the same cwd and carry a parent_thread_id, so they are skipped."""
        sessions = Path.home() / ".codex" / "sessions"
        candidates = sorted((p for p in sessions.rglob("rollout-*.jsonl") if p.stat().st_mtime >= since - 5),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates:
            with path.open(encoding="utf-8", errors="replace") as handle:
                meta = json.loads(handle.readline() or "{}").get("payload", {})
            if not meta.get("parent_thread_id") and Path(meta.get("cwd", "")).resolve() == repo.resolve():
                return path.read_text(encoding="utf-8", errors="replace")
        return ""

    @staticmethod
    def delivered(run: dict, marker: str) -> list[str]:
        """Model-visible text in the rollout (messages and tool outputs) that contains the marker."""
        found = []
        for line in run["rollout"].splitlines():
            record = json.loads(line) if line.startswith("{") else {}
            if record.get("type") != "response_item" or marker not in line:
                continue
            payload = record.get("payload", {})
            content = payload.get("content") or payload.get("output") or []
            texts = [content] if isinstance(content, str) else [c.get("text", "") for c in content if isinstance(c, dict)]
            found += [text for text in texts if marker in text]
        return found


def scenario_capture(h: CodexHarness, report: dict):
    """A real bug fix is captured: the failing first test run, the patch, and a verified successful outcome."""
    repo = h.repo("capture")
    run = h.codex_run(repo, FIX_PROMPT)
    store = h.graph(repo)
    try:
        calls = list(reversed(store.list("ToolCall")))
        report.update(seconds=run["seconds"], tool_calls=[(c.name, c.category, c.status, c.error_signature) for c in calls],
                      outcome=[(o.status, o.evidence) for o in store.list("Outcome")])
        assert run["code"] == 0, run["stderr"]
        assert len(store.list("Task")) == 1, "prompt was not captured as a task"
        assert any(c.category == "edit" and "dates.py" in c.files for c in calls), "patch to dates.py not captured"
        tests = [c for c in calls if c.category == "test"]
        assert tests and tests[0].status == "failure", "the failing first pytest run was not recorded as a failure"
        assert tests[-1].status == "success", "the passing final pytest run was not recorded as a success"
        experiences = store.list("Experience")
        assert experiences and experiences[0].status == "success", report["outcome"]
    finally:
        store.close()


def scenario_context_injection(h: CodexHarness, report: dict):
    """A similar task in a new Codex session receives the Execution Context learned from the first."""
    repo = h.root / "capture"
    subprocess.run(["git", "checkout", "--", "dates.py"], cwd=repo, check=True, env=h.env)
    run = h.codex_run(repo, "parse_date gives an off-by-one month for dates like 2023-01-02. Please fix it and run "
                            "python -m pytest -q.")
    store = h.graph(repo)
    try:
        injected = [c for c in store.list("Context") if c.injected and c.experience_ids]
        delivered = h.delivered(run, "[OpenReflex]")
        report.update(seconds=run["seconds"], context=injected[0].text if injected else None,
                      delivered_to_model=delivered[:1])
        assert run["code"] == 0, run["stderr"]
        assert injected and "dates.py" in injected[0].text, "second task was not given prior experience"
        assert any("dates.py" in text for text in delivered), "Execution Context was built but not delivered"
    finally:
        store.close()


def scenario_failure_loop_alert(h: CodexHarness, report: dict):
    """Repeated failing test runs raise one replanning alert, and it reaches the model."""
    repo = h.repo("loop", {"tests/test_external.py": ALWAYS_FAILS})
    prompt = ("tests/test_external.py checks an external sandbox that may be flaky. Without editing any files, run "
              "python -m pytest -q tests/test_external.py five separate times, as five separate commands one after "
              "another, and then report whether it ever passed.")
    run = h.codex_run(repo, prompt)
    store = h.graph(repo)
    try:
        calls = store.list("ToolCall")
        alerts = [e.alerts for e in store.list("Execution")]
        delivered = h.delivered(run, "OpenReflex:")
        report.update(seconds=run["seconds"], alerts=alerts, failures=sum(c.status == "failure" for c in calls),
                      delivered=delivered[:1])
        assert report["failures"] >= 3, "the failing test was not run (or not recorded as failing) 3+ times"
        assert any("failure_loop" in a or any(x.startswith("retry:") for x in a) for a in alerts), "no alert raised"
        assert delivered, "alert was recorded but never delivered to the model"
    finally:
        store.close()


def scenario_mcp_tools(h: CodexHarness, report: dict):
    """The MCP server from .codex/config.toml starts inside Codex and returns captured experience."""
    repo = h.root / "capture"
    run = h.codex_run(repo, "Use the openreflex MCP server's search_experience tool with query "
                            "'parse_date wrong month bug', then reply with only the files it reports.")
    items = [json.loads(line).get("payload", {}) for line in run["rollout"].splitlines() if '"response_item"' in line]
    calls = [i for i in items if "call" in i.get("type", "") and "output" not in i.get("type", "")
             and "search_experience" in json.dumps(i.get("input", i.get("arguments", "")))]
    outputs = [json.dumps(i.get("output", "")) for i in items if i.get("call_id") in {c.get("call_id") for c in calls}
               and "output" in i.get("type", "")]
    report.update(seconds=run["seconds"], mcp_calls=len(calls), mcp_output=[o[:400] for o in outputs])
    assert run["code"] == 0, run["stderr"]
    assert calls, "search_experience was not called"
    assert any("dates.py" in output for output in outputs), "MCP tool result did not include captured files"


SCENARIOS = {
    "capture": scenario_capture,
    "context-injection": scenario_context_injection,
    "failure-loop-alert": scenario_failure_loop_alert,
    "mcp-tools": scenario_mcp_tools,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--out", default="live-codex-results.json")
    args = parser.parse_args()
    harness = CodexHarness(args.keep)
    selected = [s for s in args.only.split(",") if s] or list(SCENARIOS)
    results, failed = {}, 0
    print(f"workdir: {harness.root}\ncodex: {harness.codex}\nopenreflex: {harness.exe}\n")
    for name in selected:
        report: dict = {}
        try:
            SCENARIOS[name](harness, report)
            report["status"] = "pass"
        except Exception as error:  # noqa: BLE001 - report every scenario
            failed += 1
            report.update(status="FAIL", error=f"{type(error).__name__}: {error}"[:1500])
        report["hook_errors"] = harness.errors()[-5:]
        results[name] = report
        print(f"[{report['status']}] {name} ({report.get('seconds', '?')}s) {report.get('error', '')}", flush=True)
    Path(args.out).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n{len(selected) - failed}/{len(selected)} scenarios passed; details in {args.out}")
    if not args.keep:
        shutil.rmtree(harness.root, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
