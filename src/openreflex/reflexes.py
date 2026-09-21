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


def _family(experience: Experience) -> str:
    paths = [path.lower() for path in experience.files]
    names = {PurePosixPath(path).name for path in paths}
    words = _words(experience.description)

    if "values.yaml" in names or "values.yml" in names:
        return "helm-values"
    if "chart.yaml" in names:
        return "helm-chart"
    if any("/templates/" in f"/{path}" for path in paths):
        return "helm-template"
    if any(path.endswith(".tf") or path.endswith(".tfvars") for path in paths):
        return "terraform"
    if names & {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock"}:
        return "dependencies"
    if any(part in path for path in paths for part in ("/test", "/tests/", "_test.", ".spec.", ".test.")):
        return "tests"
    if words & {"architecture", "overview", "inventory", "map", "module", "modules"}:
        return "architecture-review"
    if words & {"deploy", "deployment", "rollout", "release"}:
        return "deployment"
    if words & {"auth", "authentication", "login", "token", "tokens"}:
        return "authentication"
    if words & {"cache", "caching"}:
        return "cache"
    if words & {"config", "configuration", "settings", "workspace"}:
        return "configuration"
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
        "authentication": "Authentication fix" if experience.task_class == "debug" else "Authentication change",
        "cache": "Cache fix" if experience.task_class == "debug" else "Cache change",
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


def _state(successes: int, verified: int) -> str:
    if successes >= 4 and verified >= 2:
        return "proven"
    if successes >= 2:
        return "learned"
    return "candidate"


def _confidence(known: int, successes: int, verified: int) -> float:
    if not known:
        return 0.0
    return round(min(
        0.95,
        0.45 * (successes / known) + 0.35 * min(1.0, successes / 4) + 0.20 * min(1.0, verified / 2),
    ), 3)


def compile_for_experience(store: Store, experience: Experience, now: float) -> ProjectReflex:
    """Compile or refresh the Reflex family represented by one experience."""
    family = _family(experience)
    group = [
        item for item in store.list("Experience", "task_class", experience.task_class, limit=5000)
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

    key = f"{experience.task_mode}|{experience.task_class}|{family}"
    reflex_id = "reflex-" + hashlib.sha1(key.encode()).hexdigest()[:16]
    try:
        created_at = store.get_reflex(reflex_id).created_at
    except ValueError:
        created_at = now

    seed_counts = Counter(item.strategy for item in successes if item.strategy)
    seed_strategy = seed_counts.most_common(1)[0][0] if seed_counts else None
    descriptions = " ".join(item.description for item in successes[-20:]) or experience.description
    reflex = ProjectReflex(
        id=reflex_id,
        name=_name(family, experience),
        task_mode=experience.task_mode,
        task_class=experience.task_class,
        state=_state(len(successes), verified),
        seed_strategy=seed_strategy,
        procedure=_procedure(store, successes or group or [experience]),
        evidence_ids=[item.id for item in group[-20:]],
        support_count=len(group),
        success_count=len(successes),
        verified_count=verified,
        confidence=_confidence(len(group), len(successes), verified),
        embedding=embed(descriptions),
        file_patterns=_common_files(successes),
        created_at=created_at,
        updated_at=now,
    )
    store.put_reflex(reflex)
    return reflex


def match_reflex(store: Store, description: str, task_mode: str, task_class: str,
                 threshold: float = 0.20) -> tuple[ProjectReflex, float] | None:
    """Return the strongest learned/proven project Reflex applicable to a new task."""
    query = embed(description)
    scored: list[tuple[ProjectReflex, float]] = []
    for reflex in store.list_reflexes(task_mode=task_mode, states=_VISIBLE_STATES, limit=500):
        if reflex.task_class != task_class:
            continue
        score = similarity(query, reflex.embedding)
        if score < threshold:
            continue
        score += 0.04 if reflex.state == "proven" else 0.0
        score += min(0.06, reflex.success_count * 0.01)
        scored.append((reflex, round(score, 4)))
    return max(scored, key=lambda item: (item[1], item[0].confidence), default=None)


def visible_reflexes(store: Store) -> list[ProjectReflex]:
    return store.list_reflexes(states=_VISIBLE_STATES, limit=500)
