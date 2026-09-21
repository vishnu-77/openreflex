"""Compile repeated project executions into project-specific Reflex procedures."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from .models import Experience, ProjectReflex, ToolCall
from .routing import embed, similarity
from .store import Store

_VISIBLE_STATES = ("learned", "proven")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "for", "in", "on", "of", "this", "that", "with", "from",
    "please", "project", "repo", "repository", "change", "update", "fix", "add", "make", "work",
}


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9_]+", text.lower()) if len(word) > 2 and word not in _STOPWORDS}


def _family_hints(text: str) -> set[str]:
    words = _words(text)
    families = {
        "authentication": {
            "auth", "authentication", "login", "logout", "token", "tokens", "oauth", "jwt",
            "session", "sessions", "permission", "permissions", "authorisation", "authorization",
            "role", "roles",
        },
        "database": {"database", "schema", "migration", "migrations", "alembic", "sql", "table", "tables", "orm"},
        "ci": {"ci", "pipeline", "pipelines", "workflow", "workflows", "github", "actions"},
        "deployment": {"deploy", "deployment", "rollout", "release"},
        "cache": {"cache", "caching", "invalidate", "invalidation"},
        "configuration": {"config", "configuration", "settings", "workspace"},
        "api": {"api", "endpoint", "endpoints", "route", "routes", "handler", "handlers", "webhook"},
        "dependencies": {"dependency", "dependencies", "package", "packages", "lockfile"},
        "tests": {"test", "tests", "testing", "spec", "specs"},
        "documentation": {"docs", "documentation", "readme", "guide", "guides"},
        "architecture-review": {"architecture", "overview", "inventory", "map", "module", "modules"},
    }
    return {family for family, terms in families.items() if words & terms}


def _family(experience: Experience) -> str:
    paths = [path.lower() for path in experience.files]
    names = {PurePosixPath(path).name for path in paths}

    if "values.yaml" in names or "values.yml" in names:
        return "helm-values"
    if "chart.yaml" in names:
        return "helm-chart"
    if any("/templates/" in f"/{path}" for path in paths):
        return "helm-template"
    if any(path.endswith(".tf") or path.endswith(".tfvars") for path in paths):
        return "terraform"
    if any(path.startswith(".github/workflows/") or "/.github/workflows/" in f"/{path}" for path in paths):
        return "ci"
    if any("/migrations/" in f"/{path}" or "/migration/" in f"/{path}" for path in paths):
        return "database"
    if names & {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock"}:
        return "dependencies"
    if any(part in path for path in paths for part in ("/test", "/tests/", "_test.", ".spec.", ".test.")):
        return "tests"

    hinted = _family_hints(experience.description)
    for family in (
        "authentication", "database", "ci", "deployment", "cache", "configuration", "api",
        "dependencies", "tests", "documentation", "architecture-review",
    ):
        if family in hinted:
            return family
    return f"{experience.task_mode}-{experience.task_class}"

def _name(family: str, experience: Experience) -> str:
    fixed = {
        "helm-values": "Helm values change",
        "helm-chart": "Helm chart update",
        "helm-template": "Helm template change",
        "terraform": "Terraform change",
        "dependencies": "Dependency update",
        "tests": "Test update",
        "architecture-review": "Repository architecture review",
        "deployment": "Deployment workflow",
        "authentication": "Authentication change",
        "database": "Database change",
        "ci": "CI workflow",
        "api": "API change",
        "documentation": "Documentation workflow",
        "cache": "Cache change",
        "configuration": "Configuration change",
    }
    if family in fixed:
        return fixed[family]
    if experience.task_mode == "investigate":
        return "Project investigation"
    if experience.task_mode == "think":
        return "Project decision"
    return {
        "debug": "Project bug fix",
        "refactor": "Project refactor",
        "test": "Project test change",
    }.get(experience.task_class, "Project change")


def _collapsed_categories(calls: list[ToolCall]) -> tuple[str, ...]:
    result: list[str] = []
    for call in sorted(calls, key=lambda item: (item.started_at, item.id)):
        if call.status == "failure" or call.category in {"other", "plan"}:
            continue
        if not result or result[-1] != call.category:
            result.append(call.category)
    return tuple(result)


def _common_files(group: list[Experience]) -> list[str]:
    counts = Counter(path for item in group for path in set(item.files))
    minimum = max(2, math.ceil(len(group) / 2))
    return [path for path, count in counts.most_common(5) if count >= minimum]


def _common_modules(group: list[Experience]) -> list[str]:
    counts: Counter[str] = Counter()
    for item in group:
        seen: set[str] = set()
        for raw in item.files:
            parts = PurePosixPath(raw).parent.parts
            for depth in range(2, min(4, len(parts)) + 1):
                seen.add("/".join(parts[:depth]))
        counts.update(seen)
    minimum = max(2, math.ceil(len(group) / 2))
    eligible = [(path, count) for path, count in counts.items() if count >= minimum]
    eligible.sort(key=lambda item: (-item[1], -item[0].count("/"), item[0]))
    return [path for path, _ in eligible[:5]]


def _step(category: str, files: list[str]) -> str:
    shown = ", ".join(files[:2])
    if category == "search":
        return "Locate the relevant project area"
    if category == "read":
        return f"Inspect {shown}" if shown else "Inspect the relevant project context"
    if category == "edit":
        return f"Update {shown}" if shown else "Make the focused project change"
    if category == "test":
        return "Run the project tests"
    if category == "lint":
        return "Run the project validation checks"
    if category == "build":
        return "Build or render the project output"
    if category == "web":
        return "Check the relevant external source"
    if category == "mcp":
        return "Check the relevant project tool or source"
    if category == "vcs":
        return "Check repository state or history"
    if category == "delegate":
        return "Delegate the focused subtask"
    if category == "shell":
        return "Run the project-specific command"
    return f"Perform the {category} step"


def _procedure(store: Store, group: list[Experience]) -> list[str]:
    sequences = []
    for item in group:
        sequence = _collapsed_categories(store.find("ToolCall", execution_id=item.execution_id, limit=500))
        if sequence:
            sequences.append(sequence)
    files = _common_files(group)
    if not sequences:
        if group[0].task_mode == "investigate":
            return ["Inspect the relevant project evidence", "Cross-check the important findings", "Summarise the result"]
        if group[0].task_mode == "think":
            return ["Frame the project-specific question", "Compare the relevant constraints", "Record the decision and assumptions"]
        return ["Inspect the relevant project area", "Make the focused change", "Verify the result"]
    sequence = Counter(sequences).most_common(1)[0][0]
    steps: list[str] = []
    for category in sequence[:8]:
        step = _step(category, files if category in {"read", "edit"} else [])
        if not steps or steps[-1] != step:
            steps.append(step)
    return steps[:8]


def _state(known: int, successes: int, verified: int, previous: str | None = None) -> str:
    rate = successes / known if known else 0.0
    if successes >= 4 and verified >= 2 and rate >= 0.80:
        return "proven"
    if successes >= 2 and rate >= (2 / 3):
        return "learned"
    if previous in {"learned", "proven"} and known >= 3:
        return "stale"
    return "candidate"


def _confidence(known: int, successes: int, verified: int) -> float:
    if not known:
        return 0.0
    return round(min(
        0.95,
        0.45 * (successes / known) + 0.35 * min(1.0, successes / 4) + 0.20 * min(1.0, verified / 2),
    ), 3)


def compile_for_experience(store: Store, experience: Experience, now: float) -> ProjectReflex:
    """Compile or refresh the project family represented by one experience."""
    family = _family(experience)
    group = [
        item for item in store.list("Experience", limit=5000)
        if item.task_mode == experience.task_mode and _family(item) == family and item.status != "unknown"
    ]
    group.sort(key=lambda item: item.created_at)
    successes = [item for item in group if item.status == "success"]
    verified = 0
    for item in successes:
        try:
            outcome = store.get(item.outcome_id)
        except ValueError:
            continue
        verified += int(bool(getattr(outcome, "verified", False)))

    key = f"{experience.task_mode}|{family}"
    reflex_id = "reflex-" + hashlib.sha1(key.encode()).hexdigest()[:16]
    try:
        previous = store.get_reflex(reflex_id)
        created_at = previous.created_at
        previous_state = previous.state
    except ValueError:
        created_at = now
        previous_state = None

    seed_counts = Counter(item.strategy for item in successes if item.strategy)
    seed_strategy = seed_counts.most_common(1)[0][0] if seed_counts else None
    class_counts = Counter(item.task_class for item in (successes or group))
    primary_class = class_counts.most_common(1)[0][0] if class_counts else experience.task_class
    descriptions = " ".join(item.description for item in successes[-20:]) or experience.description
    reflex = ProjectReflex(
        id=reflex_id,
        name=_name(family, experience),
        family=family,
        task_mode=experience.task_mode,
        task_class=primary_class,
        state=_state(len(group), len(successes), verified, previous_state),
        seed_strategy=seed_strategy,
        procedure=_procedure(store, successes or group or [experience]),
        evidence_ids=[item.id for item in group[-20:]],
        support_count=len(group),
        success_count=len(successes),
        verified_count=verified,
        confidence=_confidence(len(group), len(successes), verified),
        embedding=embed(descriptions),
        file_patterns=_common_files(successes),
        module_patterns=_common_modules(successes),
        created_at=created_at,
        updated_at=now,
    )
    store.put_reflex(reflex)
    return reflex

def _reflex_family(reflex: ProjectReflex) -> str:
    if reflex.family:
        return reflex.family
    name = reflex.name.lower()
    for family in (
        "helm-values", "helm-chart", "helm-template", "terraform", "authentication", "database", "ci",
        "deployment", "cache", "configuration", "api", "dependencies", "tests", "documentation",
        "architecture-review",
    ):
        if family.replace("-", " ") in name:
            return family
    paths = [path.lower() for path in reflex.file_patterns]
    if any(PurePosixPath(path).name in {"values.yaml", "values.yml"} for path in paths):
        return "helm-values"
    if any("/templates/" in f"/{path}" for path in paths):
        return "helm-template"
    return f"{reflex.task_mode}-{reflex.task_class}"


def _locality(description: str, reflex: ProjectReflex) -> float:
    query = _words(description)
    scope = _words(" ".join([*reflex.file_patterns, *reflex.module_patterns]))
    if not query or not scope:
        return 0.0
    overlap = len(query & scope)
    return round(min(1.0, overlap / max(1, min(3, len(scope)))), 4)


def match_reflex(store: Store, description: str, task_mode: str, task_class: str,
                 threshold: float = 0.28) -> tuple[ProjectReflex, float] | None:
    """Resolve the strongest project Reflex using intent, family, locality and execution evidence."""
    query = embed(description)
    hints = _family_hints(description)
    scored: list[tuple[ProjectReflex, float]] = []

    for reflex in store.list_reflexes(task_mode=task_mode, states=_VISIBLE_STATES, limit=500):
        semantic = max(0.0, similarity(query, reflex.embedding))
        family = _reflex_family(reflex)
        family_score = 1.0 if family in hints else 0.0
        locality = _locality(description, reflex)
        class_score = 1.0 if reflex.task_class == task_class else 0.55
        evidence = reflex.confidence

        if semantic < 0.20 and family_score == 0.0 and locality < 0.34:
            continue

        score = (
            0.45 * semantic
            + 0.25 * family_score
            + 0.20 * locality
            + 0.05 * class_score
            + 0.05 * evidence
        )
        if reflex.state == "proven":
            score += 0.03
        if score < threshold:
            continue
        scored.append((reflex, round(score, 4)))

    return max(scored, key=lambda item: (item[1], item[0].confidence, item[0].success_count), default=None)

def visible_reflexes(store: Store) -> list[ProjectReflex]:
    return store.list_reflexes(states=_VISIBLE_STATES, limit=500)
