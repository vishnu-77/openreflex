import json
import subprocess

from openreflex.project_map import enrich_snapshot
from openreflex.project_memory import build_snapshot, load_snapshot
from openreflex.reflex_index import context_for_task


def test_project_map_indexes_source_symbols_and_dependencies_without_persisting_source_bodies(project):
    (project / "pyproject.toml").write_text(
        "[project]\nname='demo'\ndependencies=['pydantic>=2', 'httpx>=0.27']\n",
        encoding="utf-8",
    )
    (project / "src" / "auth").mkdir(parents=True)
    secret = "literal-secret-body-value-must-not-be-persisted"
    (project / "src" / "auth" / "token_validator.py").write_text(
        f"def validate_expired_token(token):\n    marker = '{secret}'\n    return bool(token and marker)\n",
        encoding="utf-8",
    )

    build_snapshot(project)
    snapshot = enrich_snapshot(project)
    serialized = json.dumps(snapshot)

    item = next(entry for entry in snapshot["indexed_files"] if entry["path"] == "src/auth/token_validator.py")
    deps = {entry["name"] for entry in snapshot["project_map"]["dependencies"]}

    assert item["language"] == "Python"
    assert "validate_expired_token" in item["symbols"]
    assert {"pydantic", "httpx"} <= deps
    assert secret not in serialized
    assert "return bool" not in serialized

    context = context_for_task(project, "Fix expired token validation using pydantic")
    assert "src/auth/token_validator.py" in context
    assert "validate_expired_token" in context
    assert "pydantic" in context
    assert "structural priors" in context


def _git(project, *args):
    return subprocess.run(["git", *args], cwd=project, check=True, capture_output=True, text=True)


def test_git_history_adds_bounded_cochange_signal(project):
    _git(project, "init")
    _git(project, "config", "user.email", "openreflex@example.invalid")
    _git(project, "config", "user.name", "OpenReflex Test")
    (project / "src").mkdir()
    left = project / "src" / "values.py"
    right = project / "src" / "renderer.py"

    left.write_text("VALUE = 1\n", encoding="utf-8")
    right.write_text("def render(): return 1\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "first")

    left.write_text("VALUE = 2\n", encoding="utf-8")
    right.write_text("def render(): return 2\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "second")

    build_snapshot(project)
    snapshot = enrich_snapshot(project)
    relations = snapshot["project_map"]["relationships"]

    relation = next(item for item in relations if {item["source"], item["target"]} == {"src/values.py", "src/renderer.py"})
    assert relation["type"] == "cochange"
    assert relation["count"] == 2

    context = context_for_task(project, "Change values rendering")
    assert "Git co-change signal" in context


def test_project_map_is_bounded_and_keeps_only_derived_metadata(project):
    (project / "package.json").write_text(
        json.dumps({"dependencies": {"react": "19", "zod": "4"}}), encoding="utf-8"
    )
    (project / "src").mkdir()
    for index in range(40):
        (project / "src" / f"module_{index}.ts").write_text(
            f"export function task{index}() {{ return {index}; }}\n", encoding="utf-8"
        )

    build_snapshot(project)
    snapshot = enrich_snapshot(project)

    assert len(snapshot["indexed_files"]) <= 600
    assert len(snapshot["project_map"]["dependencies"]) <= 240
    assert len(snapshot["project_map"]["relationships"]) <= 180
    assert all("content" not in entry for entry in snapshot["indexed_files"])
