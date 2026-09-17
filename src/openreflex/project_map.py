"""Bounded, local structural index for first-run OpenReflex memory.

The Project Map persists derived metadata only: project-relative paths, lightweight
symbol names, dependency names, and aggregate Git history signals. Source bodies,
command output, diffs, and transcripts are never stored.
"""

from __future__ import annotations

import ast
import itertools
import json
import os
import re
import subprocess
import time
import tomllib
from collections import Counter
from pathlib import Path

from .project_memory import load_snapshot, snapshot_path, update_state

MAP_SCHEMA = "project-map.v2"
MAX_TRACKED_FILES = 4000
MAX_INDEXED_FILES = 600
MAX_SYMBOL_FILES = 350
MAX_SYMBOLS_PER_FILE = 14
MAX_DEPENDENCIES = 240
MAX_RELATIONSHIPS = 180
MAX_MANIFEST_FILES = 240
IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".next", ".venv", "venv", "node_modules", "vendor",
    "dist", "build", "target", "coverage", ".terraform", ".tox", ".nox", "__pycache__",
}
LANGUAGES = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".c": "C", ".h": "C/C++", ".cc": "C++", ".cpp": "C++", ".hpp": "C++",
    ".tf": "Terraform", ".tpl": "Template", ".yaml": "YAML", ".yml": "YAML",
}
SOURCE_LANGUAGES = {
    "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Kotlin", "Ruby", "PHP", "C#", "C",
    "C/C++", "C++", "Terraform",
}
ROLE_WEIGHT = {
    "agent-instructions": 9, "manifest": 8, "helm-config": 8, "helm-template": 7, "test": 5,
    "ci": 4, "source": 3, "documentation": 1,
}
MANIFEST_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "Chart.yaml"}


def _run_git(project: Path, *args: str, timeout: float = 1.5) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args], capture_output=True, text=True, timeout=timeout, check=False,
        )
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _tracked_paths(project: Path) -> list[Path]:
    raw = _run_git(project, "ls-files", "-z")
    if raw:
        result = []
        for item in raw.split("\0"):
            if not item:
                continue
            path = project / item
            if path.is_file():
                result.append(path)
            if len(result) >= MAX_TRACKED_FILES:
                break
        return result

    result: list[Path] = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [name for name in dirs if name not in IGNORE_DIRS and not name.startswith(".cache")]
        base = Path(root)
        for name in files:
            path = base / name
            try:
                path.relative_to(project)
            except ValueError:
                continue
            result.append(path)
            if len(result) >= MAX_TRACKED_FILES:
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
    if "test" in name.lower() or "tests" in rel.split("/") or "spec" in rel.split("/"):
        return "test"
    if name.lower().startswith("readme") or path.suffix.lower() in {".md", ".rst"}:
        return "documentation"
    return "source"


def _read_text(path: Path, max_chars: int = 160_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def _symbols(path: Path, text: str) -> list[str]:
    language = LANGUAGES.get(path.suffix.lower())
    names: list[str] = []
    if language == "Python":
        try:
            tree = ast.parse(text)
            names = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        except (SyntaxError, ValueError):
            names = []
    elif language in {"JavaScript", "TypeScript"}:
        names = re.findall(
            r"(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|const)\s+([A-Za-z_$][\w$]*)",
            text,
        )
    elif language == "Go":
        names = [
            a or b
            for a, b in re.findall(
                r"(?m)^\s*(?:func(?:\s*\([^)]*\))?\s+([A-Za-z_]\w*)|type\s+([A-Za-z_]\w*))", text
            )
        ]
    elif language == "Rust":
        names = re.findall(r"(?m)^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_]\w*)", text)
    elif language in {"Java", "Kotlin", "C#", "C", "C/C++", "C++", "Ruby", "PHP"}:
        names = re.findall(
            r"(?m)^\s*(?:public\s+|private\s+|protected\s+|export\s+)?(?:class|interface|struct|enum|def|function)\s+([A-Za-z_]\w*)",
            text,
        )
    elif language == "Terraform":
        names = [
            f"{kind}.{name}"
            for kind, name in re.findall(r'(?m)^\s*(resource|module|variable|output)\s+"([^"]+)"', text)
        ]
    elif path.suffix.lower() == ".tpl":
        names = re.findall(r'{{-?\s*define\s+"([^"]+)"', text)
    return list(dict.fromkeys(names))[:MAX_SYMBOLS_PER_FILE]


def _manifest_paths(paths: list[Path]) -> list[Path]:
    manifests = [path for path in paths if path.name in MANIFEST_NAMES]
    return sorted(manifests, key=lambda path: (len(path.parts), path.as_posix()))[:MAX_MANIFEST_FILES]


def _dependencies(project: Path, paths: list[Path]) -> list[dict]:
    """Collect dependency names from root and nested manifests without persisting manifest bodies."""
    result: dict[tuple[str, str, str], dict] = {}

    def add(name: str, ecosystem: str, source: str) -> None:
        clean = name.strip()
        if not clean or clean.startswith(("#", "-e ", ".", "/")):
            return
        key = (ecosystem, clean.lower(), source)
        result.setdefault(key, {"name": clean[:120], "ecosystem": ecosystem, "source": source})

    for manifest in _manifest_paths(paths):
        source = manifest.relative_to(project).as_posix()
        name = manifest.name
        text = _read_text(manifest)

        if name == "pyproject.toml":
            try:
                data = tomllib.loads(text)
                project_data = data.get("project", {})
                groups = [project_data.get("dependencies", []) or []]
                groups.extend((project_data.get("optional-dependencies", {}) or {}).values())
                for group in groups:
                    for item in group:
                        if isinstance(item, str):
                            add(re.split(r"[<>=!~;\s\[]", item, 1)[0], "python", source)
            except (tomllib.TOMLDecodeError, AttributeError):
                pass
        elif name == "requirements.txt":
            for line in text.splitlines():
                add(re.split(r"[<>=!~;\s\[]", line.strip(), 1)[0], "python", source)
        elif name == "package.json":
            try:
                data = json.loads(text)
                for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    for dependency in (data.get(section) or {}):
                        add(str(dependency), "node", source)
            except (ValueError, AttributeError):
                pass
        elif name == "Cargo.toml":
            try:
                data = tomllib.loads(text)
                for section in ("dependencies", "dev-dependencies", "build-dependencies"):
                    for dependency in (data.get(section) or {}):
                        add(str(dependency), "rust", source)
            except (tomllib.TOMLDecodeError, AttributeError):
                pass
        elif name == "go.mod":
            for dependency in re.findall(r"(?m)^\s*([A-Za-z0-9._~/-]+)\s+v\d", text):
                add(dependency, "go", source)
        elif name == "Chart.yaml":
            in_dependencies = False
            for line in text.splitlines():
                if re.match(r"^dependencies\s*:\s*$", line):
                    in_dependencies = True
                    continue
                if in_dependencies and line and not line.startswith((" ", "\t", "-")):
                    in_dependencies = False
                if in_dependencies:
                    match = re.search(r"\bname\s*:\s*['\"]?([^'\"\s]+)", line)
                    if match:
                        add(match.group(1), "helm", source)

    return sorted(
        result.values(), key=lambda item: (item["ecosystem"], item["name"].lower(), item["source"])
    )[:MAX_DEPENDENCIES]


def _history(project: Path) -> tuple[Counter, list[dict]]:
    raw = _run_git(
        project, "log", "-n", "120", "--name-only", "--format=format:__OPENREFLEX_COMMIT__", timeout=2.0
    )
    if not raw:
        return Counter(), []
    commits: list[list[str]] = []
    current: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if value == "__OPENREFLEX_COMMIT__":
            if current:
                commits.append(list(dict.fromkeys(current)))
            current = []
        elif value:
            current.append(value)
    if current:
        commits.append(list(dict.fromkeys(current)))

    hotspots: Counter = Counter()
    pairs: Counter = Counter()
    for files in commits:
        bounded = [path for path in files if len(Path(path).parts) <= 12][:30]
        hotspots.update(bounded)
        for left, right in itertools.combinations(sorted(set(bounded)), 2):
            pairs[(left, right)] += 1

    relationships = [
        {"type": "cochange", "source": left, "target": right, "count": count}
        for (left, right), count in pairs.most_common(MAX_RELATIONSHIPS)
        if count >= 2
    ]
    return hotspots, relationships


def build_map(project: Path) -> dict:
    paths = _tracked_paths(project)
    hotspots, relationships = _history(project)
    records: list[dict] = []
    symbol_budget = MAX_SYMBOL_FILES

    for path in paths:
        rel = path.relative_to(project).as_posix()
        role = _role(path, project)
        language = LANGUAGES.get(path.suffix.lower())
        symbols: list[str] = []
        if symbol_budget and (language in SOURCE_LANGUAGES or role in {"helm-template", "test"}):
            symbols = _symbols(path, _read_text(path))
            symbol_budget -= 1
        try:
            stat = path.stat()
            size, mtime_ns = stat.st_size, stat.st_mtime_ns
        except OSError:
            size, mtime_ns = 0, 0
        records.append(
            {
                "path": rel,
                "role": role,
                "language": language,
                "symbols": symbols,
                "hotspot": int(hotspots.get(rel, 0)),
                "fingerprint": f"{size}:{mtime_ns}",
            }
        )

    def rank(item: dict) -> tuple:
        return (
            -ROLE_WEIGHT.get(str(item.get("role")), 0),
            -min(int(item.get("hotspot", 0)), 20),
            len(Path(str(item.get("path", ""))).parts),
            str(item.get("path", "")),
        )

    indexed = sorted(records, key=rank)[:MAX_INDEXED_FILES]
    return {
        "schema_version": MAP_SCHEMA,
        "built_at": round(time.time(), 3),
        "tracked_files": len(paths),
        "indexed_files": indexed,
        "dependencies": _dependencies(project, paths),
        "relationships": relationships,
        "hotspots": [{"path": path, "changes": count} for path, count in hotspots.most_common(40)],
    }


def enrich_snapshot(project: Path) -> dict:
    """Build the map, then merge it into the latest snapshot to preserve concurrent execution evidence."""
    project_map = build_map(project)
    latest = load_snapshot(project)
    if not latest:
        return {}

    existing = {
        str(item.get("path")): dict(item) for item in latest.get("indexed_files", []) if item.get("path")
    }
    for item in project_map["indexed_files"]:
        path = item["path"]
        merged = existing.get(path, {})
        role = merged.get("role") if merged.get("role") not in (None, "source", "execution-observed") else item["role"]
        merged.update({key: value for key, value in item.items() if key not in {"role"}})
        merged["role"] = role
        existing[path] = merged

    def rank(item: dict) -> tuple:
        empirical = 6 * int(item.get("verified_successes", 0)) + 2 * int(item.get("successful_outcomes", 0))
        return (
            -empirical,
            -ROLE_WEIGHT.get(str(item.get("role")), 0),
            -int(item.get("hotspot", 0)),
            str(item.get("path", "")),
        )

    latest["indexed_files"] = sorted(existing.values(), key=rank)[:MAX_INDEXED_FILES]
    latest["project_map"] = {
        "schema_version": MAP_SCHEMA,
        "built_at": project_map["built_at"],
        "tracked_files": project_map["tracked_files"],
        "dependencies": project_map["dependencies"],
        "relationships": project_map["relationships"],
        "hotspots": project_map["hotspots"],
    }
    path = snapshot_path(project)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.map.tmp")
    temp.write_text(json.dumps(latest, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)
    update_state(
        project,
        map_files=len(latest["indexed_files"]),
        dependencies=len(project_map["dependencies"]),
        relationships=len(project_map["relationships"]),
    )
    return latest
