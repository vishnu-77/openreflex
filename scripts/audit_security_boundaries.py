"""One-off, read-only security-boundary audit probes for OpenReflex.

Run from a checkout with: python scripts/audit_security_boundaries.py
Uses disposable directories, no agent/model inference and no real project state.
This is an audit artefact, NOT a security regression test to merge unchanged.
"""

import json
import os
import tempfile
from pathlib import Path

from openreflex.engine import Engine


def main():
    with tempfile.TemporaryDirectory(prefix="openreflex-boundary-audit-") as temp:
        root = Path(temp)
        home = root / "home"
        home.mkdir()
        (home / "config.toml").write_text("[evaluation]\nholdout_percent = 0\n", encoding="utf-8")
        os.environ["OPENREFLEX_HOME"] = str(home)
        project = root / "project"
        (project / ".git").mkdir(parents=True)
        engine = Engine(project)
        try:
            engine.prompt(
                "claude-code", "self-assert",
                "Investigate the billing status endpoint and verify its expected behaviour",
            )
            asserted = engine.record_outcome(
                "success", "the assistant says the investigation was independently verified"
            )
            assertion_without_tools = bool(
                asserted.verified
                and asserted.status == "success"
                and asserted.tool_calls == 0
            )

            for i in (1, 2):
                session = "helm-{}".format(i)
                engine.prompt(
                    "claude-code", session,
                    "Update Helm values for the worker deployment variant {}".format(i),
                )
                steps = [
                    ("Read", {"file_path": "charts/app/values.yaml"}),
                    ("Edit", {"file_path": "charts/app/values.yaml"}),
                    ("Bash", {"command": "helm lint charts/app"}),
                ]
                for pos, (name, args) in enumerate(steps):
                    external_id = "{}-{}".format(session, pos)
                    engine.tool_start("claude-code", session, external_id, name, args)
                    engine.tool_end("claude-code", session, external_id, name, args, True, None, 100)
                engine.stop("claude-code", session, assistant_completed=True)

            learned = next(
                (r for r in engine.store.list_reflexes(states=("learned", "proven"), limit=100)
                 if r.family == "helm-values"),
                None,
            )
            if learned is None:
                raise RuntimeError("Probe fixture did not produce a learned Helm reflex")
            original_support = learned.support_count
            experiences = [
                e for e in engine.store.list("Experience", limit=100)
                if "charts/app/values.yaml" in e.files
            ]
            if len(experiences) != 2:
                raise RuntimeError("Probe fixture produced {} Helm experiences".format(len(experiences)))
            removed_id = experiences[0].id
            engine.forget_experience(removed_id)
            after = engine.store.get_reflex(learned.id)
            remaining = [
                e for e in engine.store.list("Experience", limit=100)
                if "charts/app/values.yaml" in e.files
            ]
            deletion_left_stale_derived_reflex = (
                len(remaining) == 1
                and after.support_count == original_support
                and removed_id in after.evidence_ids
            )
            report = {
                "probe_version": "2026-11-14",
                "model_calls": 0,
                "self_reported_outcome_marked_verified_without_tool_calls": assertion_without_tools,
                "deleted_experience_still_in_derived_reflex": deletion_left_stale_derived_reflex,
                "reflex_support_before_deletion": original_support,
                "reflex_support_after_deletion": after.support_count,
                "remaining_helm_experiences": len(remaining),
                "scope": "isolated implementation behaviour; not a remote exploit demonstration",
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            Path("audit-security-probe-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        finally:
            engine.close()


if __name__ == "__main__":
    main()
