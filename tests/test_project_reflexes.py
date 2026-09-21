from openreflex.models import ProjectReflex
from openreflex.store import SCHEMA_VERSION, Store


def test_project_reflex_round_trip_and_schema_migration(tmp_path):
    store = Store(tmp_path / "memory.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 3
        reflex = ProjectReflex(
            id="reflex-helm-values",
            name="Helm values change",
            task_mode="build",
            task_class="debug",
            state="learned",
            seed_strategy="inspect-first",
            procedure=["Inspect values.yaml", "Make the focused change", "Verify the rendered chart"],
            evidence_ids=["exp-1", "exp-2"],
            support_count=2,
            success_count=2,
            verified_count=1,
            confidence=0.72,
            embedding=[1.0, 0.0],
            file_patterns=["values.yaml"],
            created_at=1.0,
            updated_at=2.0,
        )
        store.put_reflex(reflex)

        restored = store.get_reflex(reflex.id)
        assert restored.name == "Helm values change"
        assert restored.procedure == reflex.procedure
        assert store.list_reflexes(task_mode="build", states=("learned",)) == [restored]
    finally:
        store.close()


def test_existing_v2_database_gets_reflex_table_without_rewriting_nodes(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = Store(path)
    store.set_meta("sentinel", "kept")
    store.close()

    # Simulate an existing 0.5.x database that has not yet run the v3 migration.
    import sqlite3
    db = sqlite3.connect(path)
    db.execute("DROP TABLE project_reflexes")
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()

    upgraded = Store(path)
    try:
        assert upgraded.get_meta("sentinel") == "kept"
        assert upgraded.db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert upgraded.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_reflexes'"
        ).fetchone() is not None
    finally:
        upgraded.close()
