"""Compile repeated project executions into project-specific Reflex procedures."""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections import Counter
from pathlib import PurePosixPath

from .learning import resolutions
from .models import Experience, ProjectReflex, ToolCall
from .routing import embed, similarity
from .store import Store

_VISIBLE_STATES = ("learned", "proven")
PROJECT_ROOT_FAMILY = "project-root"
CREDIT_MODEL_VERSION = 2
CREDIT_SPINE_MIN_KNOWN = 4
CREDIT_SPINE_MIN_SUPPORT = 2
CREDIT_SPINE_MIN_ABSENT = 2
CREDIT_SPINE_THRESHOLD = 0.62
CREDIT_SPINE_MIN_CONFIDENCE = 0.50
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


def _query_hints(text: str) -> set[str]:
    """Families explicitly named by a task description, including technology-specific phrases."""
    words = _words(text)
    hints = _family_hints(text)
    if "terraform" in words:
        hints.add("terraform")
    if "helm" in words:
        if words & {"value", "values"}:
            hints.add("helm-values")
        if words & {"chart", "charts"}:
            hints.add("helm-chart")
        if words & {"template", "templates"}:
            hints.add("helm-template")
    return hints


def _scope_specificity(family: str) -> int:
    """Deterministic tie-break: concrete scopes beat the always-present project root."""
    if family in {"helm-values", "helm-chart", "helm-template", "terraform", "ci", "database", "dependencies", "tests"}:
        return 3
    if family.startswith("area:"):
        return 2
    if family == PROJECT_ROOT_FAMILY:
        return 0
    return 1


_GENERIC_AREA_TOKENS = {
    "src", "source", "docs", "doc", "helm", "terraform", "config", "configuration", "template", "templates",
    "chart", "charts", "values", "variable", "variables", "deployment", "deploy", "implementation", "plan",
    "plans", "test", "tests", "spec", "specs", "module", "modules", "file", "files",
}


def _area_scopes(paths: list[str]) -> set[str]:
    """Infer stable project-area scopes from meaningful compound path segments.

    This intentionally avoids single generic words. A path such as
    helm/bitbucket-runner/Chart.yaml and docs/bitbucket-runner-plan.md both
    reinforce area:bitbucket-runner, while generic paths such as src/config.py do not.
    """
    scopes: set[str] = set()
    for raw in paths:
        for part in PurePosixPath(raw).parts:
            stem = PurePosixPath(part).stem.lower()
            tokens = [
                token for token in re.findall(r"[a-z0-9]+", stem)
                if len(token) > 2 and token not in _GENERIC_AREA_TOKENS
            ]
            if len(tokens) >= 2:
                scopes.add("area:" + "-".join(tokens[:3]))
    return scopes


def families_for_experience(experience: Experience) -> tuple[str, ...]:
    """Return every project scope reinforced by an execution, in stable priority order."""
    paths = [path.lower() for path in experience.files]
    names = {PurePosixPath(path).name for path in paths}
    families: list[str] = []

    def add(value: str) -> None:
        if value not in families:
            families.append(value)

    if "values.yaml" in names or "values.yml" in names:
        add("helm-values")
    if "chart.yaml" in names:
        add("helm-chart")
    if any("/templates/" in f"/{path}" for path in paths):
        add("helm-template")
    if any(path.endswith(".tf") or path.endswith(".tfvars") for path in paths):
        add("terraform")
    if any(path.startswith(".github/workflows/") or "/.github/workflows/" in f"/{path}" for path in paths):
        add("ci")
    if any("/migrations/" in f"/{path}" or "/migration/" in f"/{path}" for path in paths):
        add("database")
    if names & {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock"}:
        add("dependencies")
    if any(part in path for path in paths for part in ("/test", "/tests/", "_test.", ".spec.", ".test.")):
        add("tests")
    if any(path.startswith("docs/") or path.endswith((".md", ".rst")) for path in paths):
        add("documentation")

    for family in (
        "authentication", "database", "ci", "deployment", "cache", "configuration", "api",
        "dependencies", "tests", "documentation", "architecture-review",
    ):
        if family in _query_hints(experience.description):
            add(family)

    for scope in sorted(_area_scopes(experience.files)):
        add(scope)

    if not families:
        add(f"{experience.task_mode}-{experience.task_class}")
    # Every meaningful execution also reinforces one cross-mode project Reflex.
    # Specialised families remain first so existing primary-family behaviour is preserved.
    add(PROJECT_ROOT_FAMILY)
    return tuple(families)


def _family(experience: Experience) -> str:
    """Compatibility helper: return the primary scope while compilation reinforces all scopes."""
    return families_for_experience(experience)[0]


def _name(family: str, experience: Experience) -> str:
    if family == PROJECT_ROOT_FAMILY:
        return "Project Reflex"
    if family.startswith("area:"):
        words = family.removeprefix("area:").replace("-", " ")
        return f"{words.capitalize()} work"

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


def _execution_cache(store: Store) -> tuple[dict[str, list[ToolCall]], dict[str, object]]:
    calls_by_execution: dict[str, list[ToolCall]] = {}
    for call in store.list("ToolCall", limit=100_000):
        calls_by_execution.setdefault(call.execution_id, []).append(call)
    outcomes_by_id = {outcome.id: outcome for outcome in store.list("Outcome", limit=100_000)}
    return calls_by_execution, outcomes_by_id


def _beta_rate(successes: int, trials: int) -> float:
    """Small-sample-safe success-rate estimate using a Beta(1, 1) prior."""
    return (successes + 1) / (trials + 2) if trials >= 0 else 0.5


def execution_credit_graph(
    store: Store,
    group: list[Experience],
    calls_by_execution: dict[str, list[ToolCall]] | None = None,
    outcomes_by_id: dict[str, object] | None = None,
) -> list[dict]:
    """Build an evidence-weighted execution credit graph.

    Credit is an observational attribution signal, not a causal claim. A step only
    becomes part of the replay spine when OpenReflex has both presence and absence
    evidence, enough repetitions, and a positive association with successful outcomes.
    """
    known = [item for item in group if item.status in {"success", "failure"}]
    if not known:
        return []

    if calls_by_execution is None or outcomes_by_id is None:
        cached_calls, cached_outcomes = _execution_cache(store)
        calls_by_execution = calls_by_execution or cached_calls
        outcomes_by_id = outcomes_by_id or cached_outcomes

    records: list[dict] = []
    categories: set[str] = set()
    for item in known:
        calls = sorted(
            calls_by_execution.get(item.execution_id, []),
            key=lambda call: (call.started_at, call.id),
        )
        completed = [
            call for call in calls
            if call.status != "running" and call.category not in {"other", "plan"}
        ]
        counts = Counter(call.category for call in completed)
        present = set(counts)
        categories.update(present)
        resolver_categories = {fixed.category for _, fixed in resolutions(calls)}
        verified = bool(
            item.status == "success"
            and getattr(outcomes_by_id.get(item.outcome_id), "verified", False)
        )
        records.append({
            "experience": item,
            "counts": counts,
            "present": present,
            "resolvers": resolver_categories,
            "verified": verified,
        })

    total = len(records)
    graph: list[dict] = []

    for category in sorted(categories):
        with_action = [record for record in records if category in record["present"]]
        without_action = [record for record in records if category not in record["present"]]
        support = len(with_action)
        absent = len(without_action)
        success_with = sum(record["experience"].status == "success" for record in with_action)
        success_without = sum(record["experience"].status == "success" for record in without_action)

        # Bayesian smoothing prevents 1/1 and 0/1 cohorts from looking definitive.
        with_rate = _beta_rate(success_with, support)
        without_rate = _beta_rate(success_without, absent) if absent else None
        association = (with_rate - without_rate) if without_rate is not None else 0.0

        verified_support = sum(
            record["experience"].status == "success" and record["verified"]
            for record in with_action
        )
        resolution_support = sum(category in record["resolvers"] for record in with_action)
        occurrences = sum(int(record["counts"].get(category, 0)) for record in with_action)
        redundancy = max(0.0, (occurrences - support) / occurrences) if occurrences else 0.0
        coverage = support / total

        presence_evidence = min(1.0, support / 4)
        absence_evidence = min(1.0, absent / 4) if absent else 0.0
        comparison_balance = min(presence_evidence, absence_evidence)
        verified_rate = verified_support / support if support else 0.0
        resolver_rate = resolution_support / support if support else 0.0

        # Confidence is deliberately capped when there is no counterfactual cohort.
        if absent:
            confidence = min(
                1.0,
                0.50 * comparison_balance
                + 0.25 * min(1.0, total / 8)
                + 0.15 * verified_rate
                + 0.10 * resolver_rate,
            )
        else:
            confidence = min(
                0.45,
                0.20 * presence_evidence
                + 0.15 * min(1.0, total / 8)
                + 0.07 * verified_rate
                + 0.03 * resolver_rate,
            )

        # Neutral starts at 0.5. Association drives attribution; verification and
        # resolution support increase confidence in usefulness, while repeated
        # duplicate calls reduce it.
        raw_credit = (
            0.50
            + 0.42 * association
            + 0.10 * verified_rate
            + 0.08 * resolver_rate
            + 0.04 * (coverage - 0.5)
            - 0.18 * redundancy
        )
        shrink = min(1.0, confidence + 0.20)
        credit = 0.5 + (raw_credit - 0.5) * shrink
        credit = round(max(0.0, min(1.0, credit)), 3)
        confidence = round(max(0.0, min(1.0, confidence)), 3)

        spine = (
            total >= CREDIT_SPINE_MIN_KNOWN
            and support >= CREDIT_SPINE_MIN_SUPPORT
            and absent >= CREDIT_SPINE_MIN_ABSENT
            and confidence >= CREDIT_SPINE_MIN_CONFIDENCE
            and association > 0.0
            and credit >= CREDIT_SPINE_THRESHOLD
        )
        graph.append({
            "action": category,
            "credit": credit,
            "confidence": confidence,
            "support": support,
            "known": total,
            "success_with": success_with,
            "success_rate_with": round(with_rate, 3),
            "absent": absent,
            "success_without": success_without,
            "success_rate_without": round(without_rate, 3) if without_rate is not None else None,
            "association": round(association, 3) if without_rate is not None else None,
            "counterfactual_gap": round(association, 3) if without_rate is not None else None,
            "absence_success_rate": round(without_rate, 3) if without_rate is not None else None,
            "verified_support": verified_support,
            "resolution_support": resolution_support,
            "redundancy": round(redundancy, 3),
            "evidence": "comparative" if absent else "presence-only",
            "spine": spine,
        })

    return sorted(
        graph,
        key=lambda item: (
            -int(bool(item["spine"])),
            -float(item["credit"]),
            -float(item["confidence"]),
            -int(item["support"]),
            str(item["action"]),
        ),
    )


def _credit_spine(graph: list[dict]) -> set[str]:
    return {str(item["action"]) for item in graph if item.get("spine")}


def _procedure(
    store: Store,
    group: list[Experience],
    credit_graph: list[dict] | None = None,
    calls_by_execution: dict[str, list[ToolCall]] | None = None,
) -> list[str]:
    sequences = []
    for item in group:
        calls = calls_by_execution.get(item.execution_id, []) if calls_by_execution is not None else store.find(
            "ToolCall", execution_id=item.execution_id, limit=500
        )
        sequence = _collapsed_categories(calls)
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
    spine = _credit_spine(credit_graph or [])
    if spine:
        compressed = tuple(category for category in sequence if category in spine)
        if len(compressed) >= 2:
            sequence = compressed
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


def _compile_family(
    store: Store,
    experience: Experience,
    family: str,
    now: float,
    calls_by_execution: dict[str, list[ToolCall]] | None = None,
    outcomes_by_id: dict[str, object] | None = None,
) -> ProjectReflex:
    project_scope = family.startswith("area:") or family == PROJECT_ROOT_FAMILY
    observed_group = [
        item for item in store.list("Experience", limit=5000)
        if (project_scope or item.task_mode == experience.task_mode)
        and family in families_for_experience(item)
    ]
    observed_group.sort(key=lambda item: item.created_at)
    group = [item for item in observed_group if item.status != "unknown"]
    successes = [item for item in group if item.status == "success"]
    if calls_by_execution is None or outcomes_by_id is None:
        cached_calls, cached_outcomes = _execution_cache(store)
        calls_by_execution = calls_by_execution or cached_calls
        outcomes_by_id = outcomes_by_id or cached_outcomes

    verified = sum(
        int(bool(getattr(outcomes_by_id.get(item.outcome_id), "verified", False)))
        for item in successes
    )

    reflex_mode = "project" if project_scope else experience.task_mode
    key = f"{reflex_mode}|{family}"
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
    credit_graph = execution_credit_graph(store, group, calls_by_execution, outcomes_by_id)
    reflex = ProjectReflex(
        id=reflex_id,
        name=_name(family, experience),
        family=family,
        task_mode=reflex_mode,
        task_class=primary_class,
        state=_state(len(group), len(successes), verified, previous_state),
        seed_strategy=seed_strategy,
        # Project-wide and project-area Reflexes are cross-mode memory, not one task recipe.
        # Mode-specific specialised Reflexes keep executable procedures.
        procedure=[] if project_scope else _procedure(
            store, successes or group or [experience], credit_graph, calls_by_execution
        ),
        credit_graph=credit_graph,
        credit_version=CREDIT_MODEL_VERSION,
        evidence_ids=[item.id for item in (observed_group if family == PROJECT_ROOT_FAMILY else group)[-20:]],
        support_count=len(observed_group) if family == PROJECT_ROOT_FAMILY else len(group),
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


def compile_for_experience(store: Store, experience: Experience, now: float) -> ProjectReflex:
    """Compile every project scope represented by one execution and return its primary Reflex."""
    calls_by_execution, outcomes_by_id = _execution_cache(store)
    families = families_for_experience(experience)
    compiled = [
        _compile_family(store, experience, family, now, calls_by_execution, outcomes_by_id)
        for family in families
    ]
    return compiled[0]


def ensure_project_reflex(store: Store, now: float | None = None) -> ProjectReflex | None:
    """Backfill/update the root project Reflex from all captured experiences.

    Older OpenReflex versions did not compile a root project Reflex. Reading a project
    summary is therefore also a safe migration point: existing execution evidence is
    consolidated without inventing success or verification.
    """
    experiences = sorted(store.list("Experience", limit=5000), key=lambda item: item.created_at)
    if not experiences:
        return None
    latest = experiences[-1]
    calls_by_execution, outcomes_by_id = _execution_cache(store)
    return _compile_family(
        store,
        latest,
        PROJECT_ROOT_FAMILY,
        time.time() if now is None else now,
        calls_by_execution,
        outcomes_by_id,
    )


def display_state(reflex: ProjectReflex) -> str:
    """User-facing maturity: a candidate means learning is actively underway."""
    return "learning" if reflex.state == "candidate" else reflex.state


def display_reflexes(store: Store) -> list[ProjectReflex]:
    """Return the root Reflex plus specialised Reflexes, including learning candidates."""
    root = ensure_project_reflex(store)
    items = store.list_reflexes(limit=500)
    ordered = []
    if root is not None:
        ordered.append(root)
    ordered.extend(
        item for item in items
        if (root is None or item.id != root.id) and item.state in {"candidate", "learned", "proven", "stale"}
    )
    return ordered


def reflex_summary(store: Store) -> dict[str, object]:
    """Summarise project learning without collapsing active learning to a misleading zero."""
    items = display_reflexes(store)
    root = next((item for item in items if item.family == PROJECT_ROOT_FAMILY), None)
    specialised = [item for item in items if item.family != PROJECT_ROOT_FAMILY]
    states = Counter(display_state(item) for item in specialised)
    return {
        "project": root,
        "project_state": display_state(root) if root is not None else "cold",
        "project_support": root.support_count if root is not None else 0,
        "visible": len(items),
        "specialised_total": len(specialised),
        "learning": states["learning"],
        "learned": states["learned"],
        "proven": states["proven"],
        "stale": states["stale"],
        "credit_signals": sum(len(item.credit_graph) for item in items),
        "credit_spine_actions": sum(
            sum(1 for signal in item.credit_graph if signal.get("spine"))
            for item in items
        ),
    }


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
                 threshold: float = 0.28, family_hints: set[str] | None = None) -> tuple[ProjectReflex, float] | None:
    """Resolve the strongest project Reflex using intent, family, locality and execution evidence."""
    ensure_project_reflex(store)
    query = embed(description)
    hints = _query_hints(description) | set(family_hints or ())
    # The project root is a baseline, not an intent hint; specific area/procedure Reflexes should win.
    hints.discard(PROJECT_ROOT_FAMILY)
    scored: list[tuple[ProjectReflex, float]] = []

    for reflex in store.list_reflexes(states=_VISIBLE_STATES, limit=500):
        if reflex.task_mode not in {task_mode, "project"}:
            continue
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

    return max(
        scored,
        key=lambda item: (
            item[1],
            _scope_specificity(_reflex_family(item[0])),
            item[0].confidence,
            item[0].success_count,
        ),
        default=None,
    )

def visible_reflexes(store: Store) -> list[ProjectReflex]:
    return store.list_reflexes(states=_VISIBLE_STATES, limit=500)
