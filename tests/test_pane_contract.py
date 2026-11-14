"""The Claude Code pane (plugins/openreflex/hooks/pane.tsx) reads what the Python side writes.

It has no other way to learn of a rename, so these tests hold both sides to one contract:
the state.json fields it reads, the folder name it matches projects by, and the [OpenReflex] tag.
"""
import json
import re
from pathlib import Path

import pytest

from openreflex.engine import Engine
from openreflex.project import approve
from openreflex.project_memory import read_state, state_path, update_state
from openreflex.reflex_index import sync_counts
from openreflex.store import Store

from .test_hooks import call, seed_experience

ROOT = Path(__file__).resolve().parents[1]
PANE_TYPES = ROOT / "plugins/openreflex/types/index.d.ts"
PANE = ROOT / "plugins/openreflex/hooks/pane.tsx"


@pytest.fixture
def factory(tmp_path, clock):
    database = tmp_path / "hooks.sqlite3"
    return lambda project: Engine(project, Store(database), clock=clock)


def pane_state_fields() -> set[str]:
    """The top-level fields of `ReflexState` in the pane's type contract."""
    text = PANE_TYPES.read_text(encoding="utf-8")
    body = re.search(r"export type ReflexState = \{(.*?)\n\}", text, re.S)
    assert body, "ReflexState not found in the pane's types"
    return set(re.findall(r"^  (\w+)\??:", body.group(1), re.M))


def test_every_field_the_pane_reads_is_still_written_by_python():
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src/openreflex").glob("*.py"))
    fields = pane_state_fields()
    assert {"phase", "experiences", "activity", "updated_at"} <= fields
    missing = sorted(f for f in fields if f'"{f}"' not in source and f"{f}=" not in source)
    assert missing == [], f"the pane reads state fields Python no longer writes: {missing}"


def test_state_file_has_what_the_pane_shows(project):
    approve(project)
    sync_counts(project)
    update_state(project, "watch", activity={"category": "test", "label": "TEST", "status": "running",
                                             "target": "tests/test_x.py"}, execution={"calls": 1})
    raw = json.loads(state_path(project).read_text(encoding="utf-8"))
    assert raw["schema_version"] == "openreflex-ui.v1"
    # The pane finds this file by the project's folder name, case-insensitively.
    assert raw["project"].lower() == project.name.lower()
    assert raw["phase"] == "watch"
    assert isinstance(raw["updated_at"], float)
    assert {"label", "status", "target"} <= set(raw["activity"])
    for count in ("experiences", "lessons", "reflexes_proven", "reflexes_learning", "verified"):
        assert isinstance(raw[count], int), count
    assert read_state(project) == raw


def test_state_lives_where_the_pane_looks(project, isolated_home):
    approve(project)
    update_state(project, "watch")
    path = state_path(project)
    # pane.tsx reads <OPENREFLEX_HOME>/projects/<folder>/state.json.
    assert path.name == "state.json" and path.parent.parent == isolated_home / "projects"
    assert "${home}/projects/${dir.name}/state.json" in PANE.read_text(encoding="utf-8")


def test_recalled_context_starts_with_the_tag_the_pane_reads(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)
    output = json.loads(call("claude-code", "UserPromptSubmit", {
        "session_id": "new", "cwd": str(project), "prompt": "Fix login bug: expired tokens are still accepted"}, factory))
    context = output["hookSpecificOutput"]["additionalContext"]
    assert any(line.strip().startswith("[OpenReflex]") for line in context.splitlines())
    assert "const TAG = '[OpenReflex]'" in PANE.read_text(encoding="utf-8")
