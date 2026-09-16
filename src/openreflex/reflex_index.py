"""ReflexIndex: fuse structural project memory with observed execution evidence.

Repository-derived facts remain structural priors. This module only adds explicit
execution support metadata to indexed files after an execution has completed, so
OpenReflex can progressively prefer project locations that repeatedly matter in
successful work without rewriting structural inference as historical fact.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .engine import Engine
from .project_memory import load_snapshot, snapshot_path, update_state

ROLE_BONUS = {
    "helm-config": 5.0,
    "helm-template": 4.0,
    "manifest": 3.0,
    "agent-instructions": 3.0,
    "test": 2.0,
    "ci": 1.0,
}


def _atomic_snapshot(project: Path, snapshot: dict) -> None:
    path = snapshot_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _terms(text: str) -> set[str]:
    stop = {
        "this", "that", "with", "from", "into", "when", "where", "what", "fix", "add", "make", "please",
        "project", "issue", "bug", "code", "change", "update", "implement", "create",
    }
    return {word for word in re.findall(r"[a-z0-9_./-]{3,}", text.lower()) if word not in stop}


def _evidence_state(item: dict) -> str:
    verified = int(item.get("verified_successes", 0))
    observations = int(item.get("observations", 0))
    if verified >= 2:
        return "reinforced"
    if verified:
        return "verified"
    if observations:
        return "observed"
    return "discovered"


def _counts(engine: Engine) -> dict[str, int]:
    experiences = engine.store.list("Experience", limit=5000)
    outcomes = engine.store.list("Outcome", limit=5000)
    lessons = engine.store.list("Lesson", limit=5000)
    return {
        "experiences": len(experiences),
        "verified": sum(outcome.verified for outcome in outcomes),
        "known_outcomes": sum(outcome.status != "unknown" for outcome in outcomes),
        "lessons": len(lessons),
    }


def sync_counts(project: Path) -> dict[str, int]:
    """Refresh lightweight UI counts from the local Experience Graph."""
    engine = Engine(project)
    try:
        counts = _counts(engine)
        update_state(project, **counts)
        return counts
    finally:
        engine.close()


def reinforce_files(project: Path, files: list[str], *, status: str, verified: bool, now: float | None = None) -> dict:
    """Attach outcome support to indexed project files without changing structural fact provenance."""
    snapshot = load_snapshot(project)
    if not snapshot or not files:
        return snapshot
    at = time.time() if now is None else now
    touched = {str(Path(path).as_posix()) for path in files if path}
    by_path = {str(item.get("path")): item for item in snapshot.get("indexed_files", []) if item.get("path")}

    for path in sorted(touched):
        item = by_path.get(path)
        if item is None:
            # Execution-observed files are useful memory even when the Primer did not rank them structurally.
            item = {"path": path, "role": "execution-observed", "source_hash": ""}
            snapshot.setdefault("indexed_files", []).append(item)
            by_path[path] = item
        item["observations"] = int(item.get("observations", 0)) + 1
        if status == "success":
            item["successful_outcomes"] = int(item.get("successful_outcomes", 0)) + 1
            if verified:
                item["verified_successes"] = int(item.get("verified_successes", 0)) + 1
        elif status == "failure":
            item["failed_outcomes"] = int(item.get("failed_outcomes", 0)) + 1
        item["last_observed_at"] = round(at, 3)
        item["evidence_state"] = _evidence_state(item)

    # Bound empirical additions too; structural high-signal files remain first, then execution-supported files.
    snapshot["indexed_files"] = sorted(
        snapshot.get("indexed_files", []),
        key=lambda item: (
            -int(item.get("verified_successes", 0)),
            -int(item.get("successful_outcomes", 0)),
            -int(item.get("observations", 0)),
            0 if item.get("role") != "execution-observed" else 1,
            str(item.get("path", "")),
        ),
    )[:300]
    snapshot["evidence_updated_at"] = round(at, 3)
    _atomic_snapshot(project, snapshot)
    return snapshot


def reinforce_latest_execution(project: Path, agent: str, session: str) -> dict:
    """Read the just-finished local graph and reinforce the index + presentation counts."""
    engine = Engine(project)
    try:
        execution = engine.current_execution(agent, session)
        if execution is None:
            return _counts(engine)
        outcomes = engine.store.find("Outcome", execution_id=execution.id)
        experiences = engine.store.find("Experience", execution_id=execution.id)
        outcome = outcomes[0] if outcomes else None
        experience = experiences[0] if experiences else None
        if outcome is not None and experience is not None:
            reinforce_files(project, experience.files, status=outcome.status, verified=outcome.verified,
                            now=outcome.elapsed_seconds + execution.started_at)
        counts = _counts(engine)
        update_state(project, **counts)
        return counts
    finally:
        engine.close()


def account_project_context(project: Path, agent: str, session: str, context: str) -> None:
    """Count structural context once per execution in existing context-token telemetry."""
    if not context:
        return
    engine = Engine(project)
    try:
        with engine.store.transaction():
            execution = engine.store.latest(agent, session)
            if execution is None:
                return
            marker = f"project-context:{execution.id}"
            if engine.store.get_meta(marker):
                return
            chars_per_token = engine.policy.number("context.chars_per_token")
            execution.context_tokens = int(execution.context_tokens or 0) + round(len(context) / chars_per_token)
            engine.store.put(execution)
            engine.store.set_meta(marker, "1", overwrite=False)
    finally:
        engine.close()


def context_for_task(project: Path, description: str, *, max_files: int = 6, max_commands: int = 4) -> str | None:
    """Hybrid project retrieval: lexical structure plus accumulated execution support."""
    snapshot = load_snapshot(project)
    if not snapshot:
        return None
    query = _terms(description)
    scored: list[tuple[float, dict]] = []
    for item in snapshot.get("indexed_files", []):
        path_terms = _terms(str(item.get("path", "")))
        overlap = len(query & path_terms)
        empirical = (
            4.0 * int(item.get("verified_successes", 0))
            + 1.5 * int(item.get("successful_outcomes", 0))
            + 0.25 * int(item.get("observations", 0))
            - 1.5 * int(item.get("failed_outcomes", 0))
        )
        score = overlap * 10.0 + ROLE_BONUS.get(str(item.get("role")), 0.0) + min(empirical, 12.0)
        if score > 0:
            scored.append((score, item))
    selected = [item for _, item in sorted(scored, key=lambda pair: (-pair[0], str(pair[1].get("path", ""))))[:max_files]]
    files = [str(item["path"]) for item in selected]
    commands = [item["command"] for item in snapshot.get("commands", []) if item.get("state") == "active"][:max_commands]
    supported = sum(int(item.get("verified_successes", 0)) for item in selected)

    lines = [f"Project memory: {snapshot.get('project_kind', 'software repository')}."]
    if files:
        lines.append("Structurally relevant: " + ", ".join(files) + ".")
    if commands:
        lines.append("Observed project verification: " + ", ".join(commands) + ".")
    if supported:
        lines.append(f"Execution support: selected project locations include {supported} explicit verified-success observation(s).")
    lines.append("Evidence: repository structure/config is a structural prior; execution support is counted separately.")
    return "\n".join(lines)
