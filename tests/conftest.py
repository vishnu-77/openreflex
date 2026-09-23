import itertools

import pytest

from openreflex.engine import Engine
from openreflex.store import Store


class Clock:
    def __init__(self, start: float = 1_700_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENREFLEX_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-user"))
    for name in ("OPENREFLEX_PROJECT", "CLAUDE_PROJECT_DIR", "OPENREFLEX_AUTO_APPROVE", "OPENREFLEX_DISABLE"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "home"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def engine(project, tmp_path, clock):
    engine = Engine(project, Store(tmp_path / "db.sqlite3"), clock=clock)
    yield engine
    engine.close()


_ids = itertools.count()


def run_task(engine, clock, session, prompt, script, agent="claude-code"):
    """Drives a task through the engine. script: list of (tool, arguments, success, error)."""
    messages = [engine.prompt(agent, session, prompt)]
    for tool, arguments, success, error in script:
        clock.advance(5)
        tool_id = f"{session}-{next(_ids)}"
        engine.tool_start(agent, session, tool_id, tool, arguments)
        clock.advance(3)
        messages.append(engine.tool_end(agent, session, tool_id, tool, arguments, success, error, 800))
    clock.advance(2)
    outcome = engine.stop(agent, session)
    return outcome, messages
