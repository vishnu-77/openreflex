"""Managed project memory for cold-start reduction.

Project memory is intentionally separate from execution memory. It is built from
local repository structure and configuration, carries provenance + freshness, and
never claims that a route worked until execution/outcome evidence says so.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .store import database_path

SNAPSHOT_SCHEMA = "project-memory.v1"
STATE_SCHEMA = "openreflex-ui.v1"
IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".next", ".venv", "venv", "node_modules", "vendor",
    "dist", "build", "target", "coverage", ".terraform", ".tox", ".nox", "__pycache__",
}
SOURCE_NAMES = {
    "README.md", "README.rst", "AGENTS.md", "CLAUDE.md", "Makefile", "justfile", "package.json", "pyproject.toml",
    "go.mod", "Cargo.toml", "Chart.yaml", "values.yaml", "values.schema.json", "requirements.txt", "tox.ini",
    "pytest.ini", ".pre-commit-config.yaml", "Taskfile.yml", "Taskfile.yaml",
}
COMMAND_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("helm lint", "lint", re.compile(r"\bhelm\s+lint\b", re.I)),
    ("helm template", "build", re.compile(r"\bhelm\s+template\b", re.I)),
    ("helm test", "test", re.compile(r"\bhelm\s+(?:test|unittest)\b", re.I)),
    ("helm dry-run", "build", re.compile(r"\bhelm\s+(?:install|upgrade)\b[^\n]{0,180}--dry-run\b", re.I)),
    ("ct lint", "lint", re.compile(r"\bct\s+lint\b", re.I)),
    ("ct install", "test", re.compile(r"\bct\s+install\b", re.I)),
    ("kubeconform", "lint", re.compile(r"\bkubeconform\b", re.I)),
    ("kubeval", "lint", re.compile(r"\bkubeval\b", re.I)),
    ("yamllint", "lint", re.compile(r"\byamllint\b", re.I)),
    ("pytest", "test", re.compile(r"\b(?:python\s+-m\s+)?pytest\b", re.I)),
    ("ruff", "lint", re.compile(r"\bruff\b", re.I)),
    ("npm test", "test", re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b", re.I)),
    ("npm lint", "lint", re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:lint|typecheck)\b", re.I)),
    ("npm build", "build", re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?build\b", re.I)),
    ("go test", "test", re.compile(r"\bgo\s+test\b", re.I)),
    ("cargo test", "test", re.compile(r"\bcargo\s+test\b", re.I)),
    ("cargo build", "build", re.compile(r"\bcargo\s+build\b", re.I)),
)


def memory_dir(project: Path) -> Path:
    return database_path(project).parent


def snapshot_path(project: Path) -> Path:
    return memory_dir(project) / "project-memory.json"


def state_path(project: Path) -> Path:
    return memory_dir(project) / "state.json"


def lock_path(project: Path) -> Path:
    return memory_dir(project) / "primer.lock"


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def read_state(project: Path) -> dict:
    state = read_json(state_path(project))
    return state if state.get("schema_version") == STATE_SCHEMA else {}


def update_state(project: Path, phase: str | None = None, **fields) -> dict:
    state = read_state(project)
    state.setdefault("schema_version", STATE_SCHEMA)
    state.setdefault("project", project.name)
    if phase:
        state["phase"] = phase
        state["phase_changed_at"] = round(time.time(), 3)
    state.update({key: value for key, value in fields.items() if value is not None})
    state["updated_at"] = round(time.time(), 3)
    _atomic_json(state_path(project), state)
    return state


def load_snapshot(project: Path) -> dict:
    snapshot = read_json(snapshot_path(project))
    return snapshot if snapshot.get("schema_version") == SNAPSHOT_SCHEMA else {}


def _git_head(project: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=0.35, check=False,
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40}", value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _walk(project: Path, limit: int = 2500) -> list[Path]:
    result: list[Path] = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".cache")]
        base = Path(root)
        for name in files:
            path = base / name
            try:
                rel = path.relative_to(project)
            except ValueError:
                continue
            if len(rel.parts) > 12:
                continue
            result.append(path)
            if len(result) >= limit:
                return result
    return result


def _role(path: Path, project: Path) -> str:
    rel = path.relative_to(project).as_posix()
    name = path.name
    if rel.startswith(".github/workflows/") or rel.startswith(".gitlab/"):
        return "ci"
    if name in {"AGENTS.md", "CLAUDE.md"}:
        return "agent-instructions"
    if name in {"Chart.yaml", "values.yaml", "values.schema.json"}:
        return "helm-config"
    if "/templates/" in f"/{rel}" and path.suffix in {".yaml", ".yml", ".tpl"}:
        return "helm-template"
    if name in {"package.json", "pyproject.toml", "go.mod", "Cargo.toml", "requirements.txt"}:
        return "manifest"
    if name.lower().startswith("readme"):
        return "documentation"
    if "test" in name.lower() or "tests" in rel.split("/"):
        return "test"
    return "source"


def _source_candidate(path: Path, project: Path) -> bool:
    rel = path.relative_to(project).as_posix()
    return path.name in SOURCE_NAMES or rel.startswith(".github/workflows/") or rel.startswith(".gitlab/")


def _hash_file(path: Path, max_bytes: int = 512_000) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            digest.update(handle.read(max_bytes))
    except OSError:
        return ""
    return digest.hexdigest()


def _read_source(path: Path, max_chars: int = 120_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def _project_kind(paths: list[Path]) -> tuple[str, list[str]]:
    names = {path.name for path in paths}
    suffixes = {path.suffix for path in paths}
    tech: list[str] = []
    if "Chart.yaml" in names:
        tech += ["Helm", "Kubernetes"]
    if "pyproject.toml" in names or "requirements.txt" in names:
        tech.append("Python")
    if "package.json" in names:
        tech.append("Node.js")
    if "go.mod" in names:
        tech.append("Go")
    if "Cargo.toml" in names:
        tech.append("Rust")
    if ".tf" in suffixes:
        tech.append("Terraform")
    unique = list(dict.fromkeys(tech))
    return (" / ".join(unique) if unique else "software repository", unique)


def _fact_key(kind: str, value: str, source: str) -> str:
    return hashlib.sha256(f"{kind}\0{value}\0{source}".encode()).hexdigest()[:20]


def build_snapshot(project: Path, *, now: float | None = None) -> dict:
    """Build a bounded, local, provenance-aware project-memory snapshot."""
    built_at = time.time() if now is None else now
    paths = _walk(project)
    project_kind, technologies = _project_kind(paths)
    old = load_snapshot(project)
    source_records: list[dict] = []
    facts: list[dict] = []
    commands: dict[str, dict] = {}

    for path in paths:
        if not _source_candidate(path, project):
            continue
        rel = path.relative_to(project).as_posix()
        source_hash = _hash_file(path)
        text = _read_source(path)
        source_records.append({"path": rel, "role": _role(path, project), "source_hash": source_hash})
        for command, category, pattern in COMMAND_PATTERNS:
            if pattern.search(text):
                commands.setdefault(command, {"command": command, "category": category, "source": rel,
                                              "source_hash": source_hash, "confidence": 0.95, "state": "active"})

    for technology in technologies:
        source = next((record for record in source_records if technology.lower().split(".")[0] in record["path"].lower()), "")
        source_path = source["path"] if isinstance(source, dict) else "repository-structure"
        source_hash = source.get("source_hash", "") if isinstance(source, dict) else ""
        facts.append({"id": _fact_key("technology", technology, source_path), "kind": "technology", "value": technology,
                      "source": source_path, "source_hash": source_hash, "confidence": 0.9, "state": "active",
                      "last_seen_at": round(built_at, 3)})
    for item in commands.values():
        facts.append({"id": _fact_key("verification", item["command"], item["source"]), "kind": "verification",
                      "value": item["command"], "source": item["source"], "source_hash": item["source_hash"],
                      "confidence": item["confidence"], "state": "active", "last_seen_at": round(built_at, 3)})

    active_ids = {fact["id"] for fact in facts}
    for previous in old.get("facts", []):
        if previous.get("id") not in active_ids and previous.get("state") == "active":
            stale = dict(previous)
            stale["state"] = "stale"
            stale["confidence"] = round(float(stale.get("confidence", 0.5)) * 0.5, 3)
            stale["stale_at"] = round(built_at, 3)
            facts.append(stale)

    ranked_files = sorted(
        ({"path": path.relative_to(project).as_posix(), "role": _role(path, project), "source_hash": _hash_file(path)}
         for path in paths if _role(path, project) != "source"),
        key=lambda item: ({"agent-instructions": 0, "ci": 1, "manifest": 2, "helm-config": 3, "helm-template": 4,
                           "test": 5, "documentation": 6}.get(item["role"], 9), item["path"]),
    )[:240]

    head = _git_head(project)
    digest = hashlib.sha256()
    for item in sorted(source_records, key=lambda x: x["path"]):
        digest.update(f"{item['path']}:{item['source_hash']}\n".encode())
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA,
        "generation": int(old.get("generation", 0)) + 1,
        "project": project.name,
        "project_kind": project_kind,
        "technologies": technologies,
        "git_head": head,
        "source_fingerprint": digest.hexdigest(),
        "built_at": round(built_at, 3),
        "files_seen": len(paths),
        "indexed_files": ranked_files,
        "commands": sorted(commands.values(), key=lambda item: (item["category"], item["command"])),
        "facts": facts,
    }
    _atomic_json(snapshot_path(project), snapshot)
    update_state(project, "ready", memory="ready", project_kind=project_kind,
                 facts=sum(fact.get("state") == "active" for fact in facts), indexed_files=len(ranked_files))
    return snapshot


def snapshot_is_fresh(project: Path, snapshot: dict | None = None) -> bool:
    snapshot = snapshot or load_snapshot(project)
    if not snapshot:
        return False
    current_head = _git_head(project)
    if current_head and snapshot.get("git_head"):
        return current_head == snapshot.get("git_head")
    return time.time() - float(snapshot.get("built_at", 0)) < 300


def _claim_lock(project: Path, stale_after: float = 180) -> bool:
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and time.time() - path.stat().st_mtime < stale_after:
            return False
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()} {time.time()}\n")
        return True
    except FileExistsError:
        try:
            if time.time() - path.stat().st_mtime >= stale_after:
                path.unlink(missing_ok=True)
                return _claim_lock(project, stale_after)
        except OSError:
            pass
        return False
    except OSError:
        return False


def run_worker(project: Path) -> dict:
    path = lock_path(project)
    if not path.exists() and not _claim_lock(project):
        return load_snapshot(project)
    try:
        update_state(project, "reflexing", memory="building")
        return build_snapshot(project)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def ensure_background_refresh(project: Path) -> str:
    """Return immediately; start a detached local primer only when memory is absent/stale."""
    snapshot = load_snapshot(project)
    if snapshot_is_fresh(project, snapshot):
        update_state(project, memory="ready", project_kind=snapshot.get("project_kind"),
                     facts=sum(f.get("state") == "active" for f in snapshot.get("facts", [])),
                     indexed_files=len(snapshot.get("indexed_files", [])))
        return "ready"
    if not _claim_lock(project):
        return "reflexing"
    phase = "refreshing" if snapshot else "reflexing"
    update_state(project, phase, memory="building")
    command = [sys.executable, "-m", "openreflex", "primer-worker", "--project", str(project)]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, **kwargs)  # noqa: S603 - fixed local executable + arguments
    except OSError:
        lock_path(project).unlink(missing_ok=True)
        update_state(project, "cold", memory="unavailable")
        return "cold"
    return phase


def _terms(text: str) -> set[str]:
    stop = {"this", "that", "with", "from", "into", "when", "where", "what", "fix", "add", "make", "please",
            "project", "issue", "bug", "code", "change", "update"}
    return {word for word in re.findall(r"[a-z0-9_./-]{3,}", text.lower()) if word not in stop}


def context_for_task(project: Path, description: str, *, max_files: int = 6, max_commands: int = 4) -> str | None:
    """Return a compact structural prior. Never describes project facts as proven execution success."""
    snapshot = load_snapshot(project)
    if not snapshot:
        return None
    query = _terms(description)
    scored: list[tuple[int, dict]] = []
    role_bonus = {"helm-config": 5, "helm-template": 4, "manifest": 3, "agent-instructions": 3, "test": 2, "ci": 1}
    for item in snapshot.get("indexed_files", []):
        path_terms = _terms(str(item.get("path", "")))
        overlap = len(query & path_terms)
        score = overlap * 10 + role_bonus.get(str(item.get("role")), 0)
        if score > 0:
            scored.append((score, item))
    files = [item["path"] for _, item in sorted(scored, key=lambda pair: (-pair[0], pair[1]["path"]))[:max_files]]
    commands = [item["command"] for item in snapshot.get("commands", []) if item.get("state") == "active"][:max_commands]
    lines = [f"Project memory: {snapshot.get('project_kind', 'software repository')}."]
    if files:
        lines.append("Structurally relevant: " + ", ".join(files) + ".")
    if commands:
        lines.append("Observed project verification: " + ", ".join(commands) + ".")
    lines.append("Evidence: repository structure/config only; verified execution evidence is reported separately.")
    return "\n".join(lines)
