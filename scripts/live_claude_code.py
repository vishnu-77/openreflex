"""Live end-to-end tests: real headless Claude Code sessions with OpenReflex hooked in.

Requires: `claude` (Claude Code, signed in) and `openreflex` installed in the Python running this script,
plus pytest in that environment. Uses real model calls (default model: haiku) - a full run costs a few cents.

    python scripts/live_claude_code.py [--model haiku] [--only plugin-capture,...] [--keep]

Every scenario runs in a throwaway git repo with an isolated OPENREFLEX_HOME, and asserts on the captured
Experience Graph rather than on model wording.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "openreflex"
MCP_PREFIX = "mcp__plugin_openreflex_openreflex__"

BUGGY = textwrap.dedent('''\
    """Tiny date helpers."""


    def parse_date(text):
        """Parse 'YYYY-MM-DD' into (year, month, day)."""
        year, month, day = text.split("-")
        return int(year), int(month) - 1, int(day)
''')
TESTS = textwrap.dedent('''\
    from dates import parse_date


    def test_parse_date():
        assert parse_date("2024-03-15") == (2024, 3, 15)


    def test_parse_date_january():
        assert parse_date("2023-01-02") == (2023, 1, 2)
''')
ALWAYS_FAILS = textwrap.dedent('''\
    def test_external_service_available():
        assert False, "ConnectionError: payments sandbox unreachable"
''')


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
    def __init__(self, model: str, keep: bool):
        self.model, self.keep = model, keep
        self.root = Path(tempfile.mkdtemp(prefix="openreflex-live-"))
        self.home = self.root / "home"
        self.claude = find_claude()
        self.exe = shutil.which("openreflex", path=str(Path(sys.executable).parent)) or shutil.which("openreflex")
        if not self.exe:
            raise SystemExit("openreflex is not installed in this environment")
        scripts = str(Path(self.exe).parent)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR", "PYTHONPATH"}
                    and not k.startswith("OPENREFLEX_")}
        self.env.update(OPENREFLEX_HOME=str(self.home), PATH=scripts + os.pathsep + os.environ.get("PATH", ""))

    def repo(self, name: str, extra: dict[str, str] | None = None) -> Path:
        path = self.root / name
        (path / "tests").mkdir(parents=True)
        (path / "dates.py").write_text(BUGGY, encoding="utf-8")
        (path / "tests" / "test_dates.py").write_text(TESTS, encoding="utf-8")
        (path / "conftest.py").write_text("", encoding="utf-8")
        for relative, content in (extra or {}).items():
            (path / relative).write_text(content, encoding="utf-8")
        for command in (["git", "init", "-q"], ["git", "add", "-A"],
                        ["git", "-c", "user.email=live@test", "-c", "user.name=live", "commit", "-qm", "init"]):
            subprocess.run(command, cwd=path, check=True, env=self.env)
        return path

    def cli(self, *args, cwd: Path) -> str:
        result = subprocess.run([self.exe, *args], cwd=cwd, env=self.env, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f"openreflex {args} failed: {result.stderr.decode(errors='replace')}")
        return result.stdout.decode(errors="replace")

    def claude_run(self, repo: Path, prompt: str, tools: list[str], plugin: bool = True, turns: int = 25) -> dict:
        command = [self.claude, "-p", prompt, "--model", self.model, "--output-format", "stream-json", "--verbose",
                   "--permission-mode", "acceptEdits", "--max-turns", str(turns), "--allowedTools", *tools]
        if plugin:
            command[1:1] = ["--plugin-dir", str(PLUGIN)]
        started = time.time()
        result = subprocess.run(command, cwd=repo, env=self.env, capture_output=True, timeout=600)
        stream = result.stdout.decode("utf-8", errors="replace")
        events = [json.loads(line) for line in stream.splitlines() if line.startswith("{")]
        final = next((e for e in reversed(events) if e.get("type") == "result"), {})
        return {"events": events, "raw": stream, "result": final, "seconds": round(time.time() - started, 1),
                "stderr": result.stderr.decode("utf-8", errors="replace")[-2000:], "code": result.returncode}

    def delivered_context(self, run: dict) -> list[str]:
        """Hook additionalContext the model actually received. stream-json omits these, so read the session
        transcript Claude Code writes to <config dir>/projects/<encoded cwd>/<session_id>.jsonl. <config dir>
        defaults to ~/.claude but follows CLAUDE_CONFIG_DIR - this matters when the harness itself runs
        inside a Claude Code session using a custom profile, or the child inherits one from its environment."""
        config_dir = Path(self.env["CLAUDE_CONFIG_DIR"]) if self.env.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"
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

    def graph(self, repo: Path):
        sys.path.insert(0, str(REPO / "src")) if "openreflex" not in sys.modules else None
        os.environ["OPENREFLEX_HOME"] = str(self.home)
        from openreflex.store import Store, database_path
        return Store(database_path(repo))

    def errors(self) -> list[str]:
        log = self.home / "logs" / "errors.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


PYTEST_TOOLS = ["Read", "Edit", "Grep", "Glob", "Bash(python -m pytest:*)", "Bash(pytest:*)"]
FIX_PROMPT = "The parse_date function in dates.py returns the wrong month. Fix the bug and run python -m pytest -q to verify."


def scenario_plugin_capture(h: Harness, report: dict):
    """Plugin loaded with --plugin-dir: a real bug fix is captured with an inferred successful outcome."""
    repo = h.repo("capture")
    h.cli("approve", "--project", str(repo), cwd=repo)
    run = h.claude_run(repo, FIX_PROMPT, PYTEST_TOOLS)
    store = h.graph(repo)
    try:
        tasks, calls = store.list("Task"), store.list("ToolCall")
        experiences, outcomes = store.list("Experience"), store.list("Outcome")
        report.update(seconds=run["seconds"], tool_calls=[(c.name, c.category, c.status) for c in reversed(calls)],
                      outcome=[(o.status, o.evidence, o.chosen_strategy, o.estimated_regret) for o in outcomes],
                      lessons=[lesson.text for lesson in store.list("Lesson")])
        assert run["code"] == 0, run["stderr"]
        assert len(tasks) == 1 and "parse_date" in tasks[0].description, tasks
        assert any(c.category == "edit" and "dates.py" in c.files for c in calls), "edit to dates.py not captured"
        assert any(c.category == "test" for c in calls), "pytest run not categorized as test"
        assert experiences and experiences[0].status == "success", outcomes
    finally:
        store.close()


def scenario_context_injection(h: Harness, report: dict):
    """A second, similar task in a new session receives the Execution Context built from the first."""
    repo = h.root / "capture"
    subprocess.run(["git", "checkout", "--", "dates.py"], cwd=repo, check=True, env=h.env)
    run = h.claude_run(repo, "parse_date gives an off-by-one month for dates like 2023-01-02. Please fix it and run "
                             "python -m pytest -q.", PYTEST_TOOLS)
    store = h.graph(repo)
    try:
        contexts = sorted(store.list("Context"), key=lambda c: len(c.experience_ids))
        injected = [c for c in contexts if c.injected]
        delivered = h.delivered_context(run)
        report.update(seconds=run["seconds"], context=injected[-1].text if injected else None,
                      delivered_to_model=any("[OpenReflex]" in text for text in delivered))
        assert run["code"] == 0, run["stderr"]
        assert injected and injected[-1].experience_ids, "second task was not given prior experience"
        assert "dates.py" in injected[-1].text
        assert any("[OpenReflex]" in text and "dates.py" in text for text in delivered),             "Execution Context was built but not delivered to the model"
        assert len(store.list("Experience")) == 2
    finally:
        store.close()


def scenario_failure_loop_alert(h: Harness, report: dict):
    """Repeated failing test runs trigger exactly one replanning alert that reaches the model."""
    repo = h.repo("loop", {"tests/test_external.py": ALWAYS_FAILS})
    h.cli("approve", "--project", str(repo), cwd=repo)
    prompt = ("tests/test_external.py checks an external sandbox that may be flaky. Without editing any files, run "
              "python -m pytest -q tests/test_external.py up to five separate times, one after another, "
              "and then report whether it ever passed.")
    run = h.claude_run(repo, prompt, ["Bash(python -m pytest:*)"], turns=15)
    store = h.graph(repo)
    try:
        executions = store.list("Execution")
        calls = store.list("ToolCall")
        report.update(seconds=run["seconds"], alerts=[e.alerts for e in executions],
                      failures=sum(c.status == "failure" for c in calls),
                      delivered=[t for t in h.delivered_context(run) if t.startswith("OpenReflex:")])
        assert sum(c.status == "failure" for c in calls) >= 3, "model did not run the failing test 3+ times"
        assert any("failure_loop" in e.alerts for e in executions), "no failure-loop alert raised"
        assert report["delivered"], "alert was recorded but never delivered to the model"
        assert any("Recommendation:" in text for text in report["delivered"]), "no continue/pivot/stop recommendation delivered"
        assert all(e.verdicts for e in executions if "failure_loop" in e.alerts), "verdict not recorded"
    finally:
        store.close()


def scenario_mcp_tools(h: Harness, report: dict):
    """The plugin's MCP server starts inside Claude Code and its tools return captured experience and a verdict."""
    repo = h.root / "capture"
    prompt = (f"Call the {MCP_PREFIX}search_experience tool with query 'parse_date wrong month bug', then call "
              f"{MCP_PREFIX}check_progress. Reply with only the list of files search_experience reports and the "
              "first line check_progress returns.")
    run = h.claude_run(repo, prompt, [f"{MCP_PREFIX}search_experience", f"{MCP_PREFIX}check_progress"], turns=8)
    used = [block for event in run["events"] if event.get("type") == "assistant"
            for block in event.get("message", {}).get("content", []) if block.get("type") == "tool_use"]
    report.update(seconds=run["seconds"], tools_called=[b.get("name") for b in used],
                  answer=run["result"].get("result", "")[:300])
    assert any(b.get("name") == f"{MCP_PREFIX}search_experience" for b in used), "MCP tool was not available/called"
    assert "dates.py" in run["raw"], "MCP tool result did not include captured files"
    assert any(b.get("name") == f"{MCP_PREFIX}check_progress" for b in used), "check_progress was not called"
    assert "Recommendation:" in run["raw"], "check_progress did not return a recommendation"


def scenario_project_install(h: Harness, report: dict):
    """`openreflex install claude-code` (no plugin) captures work through project settings alone."""
    repo = h.repo("installed")
    report["install_output"] = h.cli("install", "claude-code", "--project", str(repo), cwd=repo).strip()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=h.env)
    run = h.claude_run(repo, FIX_PROMPT, PYTEST_TOOLS, plugin=False)
    store = h.graph(repo)
    try:
        calls = store.list("ToolCall")
        report.update(seconds=run["seconds"], tool_calls=len(calls),
                      outcome=[(o.status, o.evidence) for o in store.list("Outcome")])
        assert run["code"] == 0, run["stderr"]
        assert calls, "project-level hooks did not capture any tool calls"
    finally:
        store.close()


SCENARIOS = {
    "plugin-capture": scenario_plugin_capture,
    "context-injection": scenario_context_injection,
    "failure-loop-alert": scenario_failure_loop_alert,
    "mcp-tools": scenario_mcp_tools,
    "project-install": scenario_project_install,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--only", default="")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--out", default="live-results.json")
    args = parser.parse_args()
    harness = Harness(args.model, args.keep)
    selected = [s for s in args.only.split(",") if s] or list(SCENARIOS)
    results, failed = {}, 0
    print(f"workdir: {harness.root}\nclaude: {harness.claude}\nopenreflex: {harness.exe}\n")
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
        print(f"[{report['status']}] {name} ({report.get('seconds', '?')}s) {report.get('error', '')}")
    Path(args.out).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n{len(selected) - failed}/{len(selected)} scenarios passed; details in {args.out}")
    if not args.keep:
        shutil.rmtree(harness.root, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
