import json

from openreflex.project_memory import build_snapshot, context_for_task, load_snapshot


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
