import json
import os
import time

from openreflex.project_memory import (
    _acquire_state_lock,
    _release_state_lock,
    build_snapshot,
    context_for_task,
    load_snapshot,
    state_lock_path,
)


def _helm_project(project):
    (project / "charts" / "app" / "templates").mkdir(parents=True)
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / "charts" / "app" / "Chart.yaml").write_text("apiVersion: v2\nname: app\n", encoding="utf-8")
    (project / "charts" / "app" / "values.yaml").write_text("imagePullSecrets: []\n", encoding="utf-8")
    (project / "charts" / "app" / "values.schema.json").write_text('{"type":"object"}\n', encoding="utf-8")
    (project / "charts" / "app" / "templates" / "deployment.yaml").write_text("kind: Deployment\n", encoding="utf-8")
    (project / ".github" / "workflows" / "ci.yml").write_text(
        "steps:\n  - run: helm lint ./charts/app\n  - run: helm template app ./charts/app | kubeconform\n",
        encoding="utf-8",
    )


def test_primer_builds_provenance_aware_helm_memory_without_raw_content(project):
    _helm_project(project)
    secret = "super-secret-value-that-must-not-enter-memory"
    (project / "README.md").write_text(f"Run helm lint before release. Internal note: {secret}\n", encoding="utf-8")

    snapshot = build_snapshot(project, now=100)

    assert snapshot["project_kind"] == "Helm / Kubernetes"
    commands = {item["command"] for item in snapshot["commands"]}
    assert {"helm lint", "helm template", "kubeconform"} <= commands
    assert all(item["source"] and item["source_hash"] for item in snapshot["commands"])
    assert secret not in json.dumps(snapshot)
    assert not any("content" in item for item in snapshot["indexed_files"])


def test_removed_project_fact_becomes_stale_instead_of_remaining_active(project):
    _helm_project(project)
    build_snapshot(project, now=100)
    workflow = project / ".github" / "workflows" / "ci.yml"
    workflow.unlink()

    second = build_snapshot(project, now=200)
    stale = [fact for fact in second["facts"] if fact["kind"] == "verification" and fact["state"] == "stale"]

    assert stale
    assert all(fact["confidence"] < 0.95 for fact in stale)


def test_task_context_is_compact_and_explicitly_structural(project):
    _helm_project(project)
    build_snapshot(project)

    context = context_for_task(project, "Fix imagePullSecrets rendering in the deployment template")

    assert context is not None
    assert "Helm / Kubernetes" in context
    assert "deployment.yaml" in context
    assert "helm lint" in context
    assert "repository structure/config only" in context
    assert "worked previously" not in context


def test_snapshot_round_trip_uses_project_local_memory_directory(project):
    _helm_project(project)
    built = build_snapshot(project)
    loaded = load_snapshot(project)
    assert loaded["source_fingerprint"] == built["source_fingerprint"]
    assert loaded["generation"] == 1


def test_default_timeout_reaches_stale_lock_reclaim(project):
    """A lock abandoned by a crashed process must be reclaimed before a default caller times out."""
    path = state_lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("99999 0\n", encoding="utf-8")
    old = time.time() - 5
    os.utime(path, (old, old))

    acquired = _acquire_state_lock(project)  # default timeout, must not raise TimeoutError
    try:
        assert acquired == path
    finally:
        _release_state_lock(acquired)


def test_stale_reclaim_never_fires_for_a_freshly_held_lock(project):
    """Normal, briefly-held contention must not be mistaken for an abandoned lock."""
    path = state_lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()} {time.time()}\n", encoding="utf-8")

    try:
        _acquire_state_lock(project, timeout=0.05)
        assert False, "expected TimeoutError while the lock is freshly held"
    except TimeoutError:
        pass
    finally:
        path.unlink(missing_ok=True)
