"""Stress and robustness: parallel hook processes, retrieval at scale, hostile payloads."""

import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from openreflex import hooks
from openreflex.engine import Engine
from openreflex.models import Experience
from openreflex.project import approve
from openreflex.routing import embed
from openreflex.store import Store, database_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_parallel_hook_processes_lose_no_writes(isolated_home, project):
    approve(project)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "OPENREFLEX_HOME": str(isolated_home)}
    base = {"session_id": "parallel", "cwd": str(project)}

    def hook(event, payload):
        return subprocess.run([sys.executable, "-m", "openreflex", "hook", "claude-code", event],
                              input=json.dumps(payload).encode(), capture_output=True, env=env, timeout=60)

    hook("UserPromptSubmit", {**base, "prompt": "Parallelize the thumbnail generation pipeline safely"})

    def pair(index):
        payload = {**base, "tool_name": "Grep", "tool_input": {"pattern": f"p{index}"}, "tool_use_id": f"t{index}"}
        first = hook("PreToolUse", payload)
        second = hook("PostToolUse", {**payload, "tool_response": {"matches": index}})
        return first.returncode, second.returncode

    with ThreadPoolExecutor(12) as pool:
        codes = list(pool.map(pair, range(24)))
    assert all(code == (0, 0) for code in codes)
    store = Store(database_path(project))
    calls = store.list("ToolCall")
    assert len(calls) == 24 and all(call.status == "success" for call in calls)
    store.close()
    assert not (isolated_home / "logs" / "errors.log").exists()


def test_prompt_latency_with_thousands_of_experiences(tmp_path, project, clock):
    engine = Engine(project, Store(tmp_path / "big.sqlite3"), clock=clock)
    rng = random.Random(7)
    words = "auth billing cache export parser webhook token session invoice upload retry queue schema".split()
    with engine.store.transaction():
        for i in range(3000):
            description = f"Fix {' '.join(rng.sample(words, 4))} issue {i}"
            engine.store.put(Experience(task_id=f"t{i}", execution_id=f"e{i}", outcome_id=f"o{i}", description=description,
                                        task_class="debug", strategy=rng.choice(["test-first", "inspect-first"]),
                                        status=rng.choice(["success", "failure"]), elapsed_seconds=300, tool_calls=12,
                                        output_tokens_estimate=5000, files=["src/a.py"], embedding=embed(description),
                                        created_at=clock.now))
    start = time.perf_counter()
    context = engine.prompt("claude-code", "big", "Fix auth token session issue in the login flow")
    elapsed = time.perf_counter() - start
    engine.close()
    assert context is not None
    assert elapsed < 5, f"prompt took {elapsed:.2f}s with 3000 experiences"


def _junk(rng: random.Random, depth: int = 0):
    choices = [None, True, 0, -1, 3.5, "", "x" * rng.randint(1, 5000), "\u00e9\u2603\U0001f600 \x00", "../../etc/passwd",
               "/tmp/" + "y" * 300 + "/deep", "/tmp/nul\x00byte",
               "C:\\Windows\\system32", ["a", 1, None], {"nested": {"file_path": "../../x"}}]
    if depth < 2:
        choices.append({k: _junk(rng, depth + 1) for k in rng.sample(["command", "file_path", "path", "input", "q"], 2)})
    return rng.choice(choices)


def test_hostile_payloads_never_break_any_agent(isolated_home, project):
    approve(project)
    rng = random.Random(1234)
    events = {"claude-code": list(hooks.CLAUDE_KINDS), "codex": list(hooks.CLAUDE_KINDS),
              "cursor": list(hooks.CURSOR_KINDS), "opencode": list(hooks.OPENCODE_KINDS)}
    fields = ["session_id", "conversation_id", "prompt", "tool_name", "tool", "tool_input", "args", "tool_use_id",
              "call_id", "tool_response", "tool_output", "error", "error_message", "output_chars", "workspace_roots"]
    for _ in range(400):
        agent = rng.choice(list(events))
        event = rng.choice(events[agent])
        payload = {name: _junk(rng) for name in rng.sample(fields, rng.randint(0, len(fields)))}
        payload["cwd"] = str(project) if rng.random() < 0.8 else _junk(rng)
        if rng.random() < 0.7:
            payload["session_id"] = payload["conversation_id"] = f"fuzz-{rng.randint(0, 3)}"
        raw = json.dumps(payload) if rng.random() < 0.9 else json.dumps(payload)[: rng.randint(0, 50)]
        output = hooks.safe_handle(agent, event, raw)
        assert isinstance(output, str)
        if agent == "cursor":
            json.loads(output)
        elif output:
            assert isinstance(json.loads(output), dict)
    # Only unparseable JSON may be rejected; wrong-typed fields must be coerced, not drop the event.
    log = isolated_home / "logs" / "errors.log"
    logged = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert all("JSONDecodeError" in line for line in logged), [x for x in logged if "JSONDecodeError" not in x][:3]
    # The graph must still be consistent and usable afterwards.
    store = Store(database_path(project))
    for call in store.list("ToolCall", limit=10_000):
        assert store.exists(call.execution_id)
    store.close()


def test_well_formed_unusual_payloads_log_no_errors(isolated_home, project):
    approve(project)
    base = {"session_id": "u", "cwd": str(project)}
    unusual = [
        ("UserPromptSubmit", {**base, "prompt": "R\u00e9pare le bug \u2603 dans l'export CSV \U0001f600 maintenant"}),
        ("PreToolUse", {**base, "tool_name": "mcp__github__create_issue", "tool_input": {"body": "x" * 200_000},
                        "tool_use_id": "1"}),
        ("PostToolUse", {**base, "tool_name": "mcp__github__create_issue", "tool_input": {"body": "x" * 200_000},
                         "tool_use_id": "1", "tool_response": [{"type": "text", "text": "ok"}]}),
        ("PostToolUse", {**base, "tool_name": "Bash", "tool_input": "echo not-a-dict", "tool_use_id": "2",
                         "tool_response": "plain string"}),
        ("PostToolUseFailure", {**base, "tool_name": "Read", "tool_input": {"file_path": "/outside/project.txt"},
                                "tool_use_id": "3", "error": "", "is_interrupt": True}),
        ("PreCompact", {**base, "trigger": "auto"}),
        ("Stop", {**base, "stop_hook_active": True}),
        ("SessionEnd", {**base, "reason": "other"}),
    ]
    for event, payload in unusual:
        hooks.safe_handle("claude-code", event, json.dumps(payload))
    log = isolated_home / "logs" / "errors.log"
    assert not log.exists(), log.read_text(encoding="utf-8") if log.exists() else ""
