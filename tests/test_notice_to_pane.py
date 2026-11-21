"""OpenReflex's notices for the person go to the side pane, never into the session transcript, and nothing the
model is given (additionalContext) or a refusal (permissionDecision) is touched on the way out."""
import json

from openreflex.entrypoint import FLOW_KEEP, notice_to_pane
from openreflex.project import approve
from openreflex.project_memory import read_state

RECAP = "↺ OpenReflex · COMPLETE\nsuccess · test-first · 8 calls"


def test_a_recap_leaves_the_session_and_lands_in_the_pane_state(project, isolated_home):
    approve(project)
    out = json.dumps({"systemMessage": RECAP,
                      "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "[OpenReflex] hint"}})
    left = json.loads(notice_to_pane(project, out, enabled=True))
    assert "systemMessage" not in left
    assert left["hookSpecificOutput"]["additionalContext"] == "[OpenReflex] hint", "model context is untouched"
    assert [item["text"] for item in read_state(project)["flow"]] == [RECAP]


def test_a_notice_alone_leaves_no_output_at_all(project, isolated_home):
    approve(project)
    assert notice_to_pane(project, json.dumps({"systemMessage": RECAP}), enabled=True) == ""


def test_output_without_a_notice_passes_through_byte_for_byte(project, isolated_home):
    deny = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": "same failing call"}})
    assert notice_to_pane(project, deny, enabled=True) == deny
    assert notice_to_pane(project, "", enabled=True) == ""


def test_an_off_project_shows_nothing_and_stores_nothing(project, isolated_home):
    assert notice_to_pane(project, json.dumps({"systemMessage": "↺ OpenReflex · OFF"}), enabled=False) == ""
    assert "flow" not in read_state(project)


def test_the_flow_keeps_only_the_newest(project, isolated_home):
    approve(project)
    for index in range(FLOW_KEEP + 5):
        notice_to_pane(project, json.dumps({"systemMessage": f"recap {index}"}), enabled=True)
    flow = read_state(project)["flow"]
    assert len(flow) == FLOW_KEEP and flow[-1]["text"] == f"recap {FLOW_KEEP + 4}"
