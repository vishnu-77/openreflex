from openreflex.reflexes import (
    PROJECT_ROOT_FAMILY,
    display_state,
    ensure_project_reflex,
    reflex_summary,
)
from openreflex.store import Store

from .test_project_reflexes import _experience


def test_root_project_reflex_exists_after_first_experience(tmp_path):
    store = Store(tmp_path / "root.sqlite3")
    try:
        experience, outcome, calls = _experience(1)
        store.put(outcome)
        store.put(experience)
        for call in calls:
            store.put(call)

        root = ensure_project_reflex(store, now=10)

        assert root is not None
        assert root.family == PROJECT_ROOT_FAMILY
        assert root.task_mode == "project"
        assert root.support_count == 1
        assert root.success_count == 1
        assert root.state == "candidate"
        assert display_state(root) == "learning"
    finally:
        store.close()


def test_existing_history_backfills_root_project_reflex_without_new_task(tmp_path):
    store = Store(tmp_path / "backfill.sqlite3")
    try:
        for index in range(1, 4):
            experience, outcome, calls = _experience(index, verified=False)
            store.put(outcome)
            store.put(experience)
            for call in calls:
                store.put(call)

        assert not any(item.family == PROJECT_ROOT_FAMILY for item in store.list_reflexes(limit=100))

        summary = reflex_summary(store)
        root = summary["project"]

        assert root is not None
        assert root.family == PROJECT_ROOT_FAMILY
        assert root.support_count == 3
        assert root.success_count == 3
        assert root.verified_count == 0
        assert summary["project_state"] == "learned"
        assert summary["project_support"] == 3
    finally:
        store.close()
