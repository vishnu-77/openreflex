"""Hints that land when rediscovery starts, never point at deleted files, carry what checks caught, and are judged
by a fair comparison: calls before the first edit, with a hint against held-out tasks that would have got one."""
from openreflex.metrics import MIN_HINT_SIDE, evidence, verdict
from openreflex.project import approve

from .test_holdout_pipeline import holdout
from .test_hooks import seed_experience
from .test_phase_b import EDIT_AUTH, EDIT_TEST, LOGIN, PYTEST, READ_AUTH, factory, files_on_disk, task  # noqa: F401

SKEW = "Make the token refresh endpoint honour the clock skew"


def test_a_first_search_points_to_the_file_its_pattern_names(project, factory, clock):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    out = task(project, factory, clock, "new", SKEW, [("Grep", {"pattern": "def auth_check"}), READ_AUTH])
    hint = out["tools"][0]
    assert hint.startswith("[OpenReflex] Earlier tasks matching this search worked on: ")
    assert "src/auth.py (2 tasks)" in hint and "tests/test_auth.py (2 tasks)" in hint  # tied counts: any order
    assert out["tools"][1] == "", "still once per task"


def test_a_search_naming_no_known_file_waits_for_the_first_file(project, factory, clock):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    out = task(project, factory, clock, "new", SKEW, [("Grep", {"pattern": "billing"}), READ_AUTH])
    assert out["tools"][0] == ""
    assert "tests/test_auth.py (2 tasks)" in out["tools"][1]


def test_deleted_files_are_never_pointed_at(project, factory, clock):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    (project / "tests/test_auth.py").unlink()
    out = task(project, factory, clock, "new", SKEW, [READ_AUTH])
    assert out["tools"] == [""], "the only co-worked file is gone, so there is nothing true to say"


def test_the_hint_says_what_checks_caught_in_those_tasks(project, factory, clock):
    approve(project)
    seed_experience(project, factory, clock)  # pytest failed, src/auth.py edited, pytest passed
    task(project, factory, clock, "s1", LOGIN, [EDIT_AUTH, EDIT_TEST])
    out = task(project, factory, clock, "new", SKEW, [READ_AUTH])
    assert "check failed and was then fixed in 1 of those task:" in out["tools"][0]


def test_evidence_compares_calls_before_the_first_edit(project, factory, clock, isolated_home):
    approve(project)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, PYTEST])
    task(project, factory, clock, "shown", SKEW, [READ_AUTH, READ_AUTH, EDIT_TEST])
    holdout(isolated_home, 100)
    task(project, factory, clock, "held", SKEW, [READ_AUTH, READ_AUTH, READ_AUTH, EDIT_TEST])
    ev = evidence(factory(project))
    # s1 (pointed from s0) edits first: 0 calls before its edit; "shown" reads twice first.
    assert ev["first_edit"] == {"shown": 2, "held_out": 1, "shown_median": 1.0, "held_out_median": 3}
    assert ev["verdict"]["state"] == "early" and "Too early to tell" in ev["verdict"]["line"]


def test_the_verdict_claims_no_more_than_the_data():
    pointers = {"shown": 30, "used": 12, "held_out": 12, "held_out_used": 3}
    side = {"shown": MIN_HINT_SIDE, "held_out": MIN_HINT_SIDE}
    assert verdict(pointers, {**side, "shown_median": 3, "held_out_median": 6})["state"] == "helping"
    assert verdict(pointers, {**side, "shown_median": 6, "held_out_median": 6})["state"] == "not_helping"
    early = verdict(pointers, {"shown": 30, "held_out": 2, "shown_median": 1, "held_out_median": 9})
    assert early["state"] == "early", "a big gap on two held-out tasks is not evidence"
    assert all("sav" not in v["line"].lower() for v in (early,))


def test_folders_are_never_pointed_at(project, factory, clock):
    approve(project)
    (project / "src" / "auth").mkdir(parents=True, exist_ok=True)
    for index in range(2):
        task(project, factory, clock, f"s{index}", LOGIN, [EDIT_AUTH, EDIT_TEST, ("Glob", {"pattern": "*.py", "path": "src/auth"})])
    out = task(project, factory, clock, "new", SKEW, [READ_AUTH])
    assert "tests/test_auth.py" in out["tools"][0] and "src/auth (" not in out["tools"][0]
