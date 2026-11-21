"""The walkthrough a user sees, end to end: a start recap naming the file a known fix was made in, a pivot to
test-first once exploration stalls, and a completion that says what was learned."""
import json

import pytest

from openreflex.decision import DecisionSnapshot
from openreflex.engine import Engine
from openreflex.project import approve
from openreflex.store import Store

from .test_hooks import call

TEST = "python -m pytest tests/test_auth.py -q"
FAIL = ("Bash", {"command": TEST}, "E   AssertionError: expired token accepted\n1 failed")
PASS = ("Bash", {"command": TEST}, None)
EDIT = ("Edit", {"file_path": "src/auth/session.py"}, None)


def read(path):
    return ("Read", {"file_path": path}, None)


@pytest.fixture
def factory(tmp_path, clock):
    return lambda project: Engine(project, Store(tmp_path / "flow.sqlite3"), clock=clock)


def shown(output: str) -> str:
    """What the user sees: the hook's systemMessage."""
    return json.loads(output).get("systemMessage", "") if output else ""


def run(project, factory, clock, session, prompt, steps):
    base = {"session_id": session, "cwd": str(project)}
    seen = [shown(call("claude-code", "UserPromptSubmit", {**base, "prompt": prompt}, factory))]
    for index, (tool, arguments, error) in enumerate(steps):
        clock.advance(25)
        payload = {**base, "tool_name": tool, "tool_input": arguments, "tool_use_id": f"{session}-{index}"}
        call("claude-code", "PreToolUse", payload, factory)
        event = "PostToolUseFailure" if error else "PostToolUse"
        extra = {"error": error} if error else {"tool_response": {"stdout": "ok"}}
        seen.append(shown(call("claude-code", event, {**payload, **extra}, factory)))
    seen.append(shown(call("claude-code", "Stop", base, factory)))
    clock.advance(600)
    return seen


def test_the_walkthrough(project, factory, clock):
    for path in ("src/auth/session.py", "src/auth/validator.py", "tests/test_auth.py"):
        (project / path).parent.mkdir(parents=True, exist_ok=True)
        (project / path).write_text("", encoding="utf-8")
    approve(project)
    for n in range(2):  # earlier: the test showed the bug and an edit in session.py fixed it
        run(project, factory, clock, f"old{n}", "Fix the login bug where expired session tokens are still accepted",
            [FAIL, read("src/auth/session.py"), EDIT, PASS])
    explore = [read("src/auth/session.py"), read("src/auth/validator.py"), read("tests/test_auth.py")] + \
              [("Grep", {"pattern": w}, None) for w in ("expires", "token_ttl", "is_valid", "utcnow", "leeway", "refresh")] + \
              [read(f) for f in ("src/auth/models.py", "src/auth/config.py", "src/auth/jwt.py", "src/app.py", "README.md",
                                 "docs/auth.md")]
    seen = run(project, factory, clock, "new", "fix expired authentication tokens still being accepted",
               explore + [FAIL, EDIT, PASS])

    start = seen[0].splitlines()
    assert start[0].startswith("↺ OpenReflex · ")
    assert start[1].startswith("2 experiences · test-first ") and start[1].endswith("context tokens")
    assert start[2] == "OpenReflex context → likely src/auth/session.py · test-first recommended"

    stall = next(text for text in seen[1:16] if text)
    assert seen.index(stall) == 15, "with a known fix, 15 exploring calls is a stall"
    assert stall.splitlines()[1] == "15 calls · budget 50% · pivot → test-first"

    done = seen[-1].splitlines()
    assert done[0] == "↺ OpenReflex · COMPLETE"
    assert done[1].startswith("success · test-first · 18 calls")
    assert done[2] == ('learned → "AssertionError: expired token accepted" (from test) was resolved by an edit in '
                       "src/auth/session.py")


def test_without_a_known_fix_exploration_gets_more_room(project, factory, clock):
    approve(project)
    explore = [read(f"src/m{i}.py") for i in range(15)]
    seen = run(project, factory, clock, "new", "fix expired authentication tokens still being accepted", explore)
    assert not any(seen[1:16]), "no fix to point at: reading is how the work starts"


def test_snapshots_from_a_newer_writer_still_load():
    snapshot = DecisionSnapshot(timestamp=0, phase="start", action="recommend", policy_version="v", policy_sources=(),
                                strategy="test-first", next_best_strategy=None, reflex_score=50, success_probability=None,
                                decision_confidence=0.5, evidence_count=0, evidence_quality=0, evidence_relevance=0,
                                route_advantage=0, uncertainty=0, expected_regret=None, estimated_tool_calls=None,
                                estimated_tokens=None, context_tokens=0, budget_used=0, budget_pressure=0)
    assert DecisionSnapshot.from_dict({**snapshot.as_dict(), "added_later": 1}) == snapshot
