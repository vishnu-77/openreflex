import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "live_cold_start_eval.py"
SPEC = importlib.util.spec_from_file_location("openreflex_live_eval", SCRIPT)
LIVE_EVAL = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(LIVE_EVAL)


def test_click_live_eval_manifest_is_pinned_and_unambiguous():
    manifest = LIVE_EVAL._load_manifest(ROOT / "evals" / "cold_start" / "click.json")
    assert manifest["name"] == "click-cold-start-v1"
    assert manifest["repository"]["name"] == "pallets/click"
    assert len(manifest["repository"]["commit"]) == 40
    assert manifest["claude_code_version"] == "2.1.278"
    assert manifest["model"] == "claude-sonnet-4-6"

    tasks = manifest["tasks"]
    assert len(tasks) == 3
    assert len({task["name"] for task in tasks}) == 3
    assert {task["target"] for task in tasks} == {
        "src/click/shell_completion.py",
        "src/click/types.py",
        "src/click/formatting.py",
    }
    for task in tasks:
        assert task["target"] not in task["prompt"], "the prompt must not reveal the answer path"
        assert "Without editing any files" in task["prompt"]


def test_usage_tokens_counts_all_reported_model_token_classes():
    usage = {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_creation_input_tokens": 30,
        "cache_read_input_tokens": 50,
    }
    assert LIVE_EVAL._usage_tokens(usage) == 200
    assert LIVE_EVAL._usage_tokens({}) is None
    assert LIVE_EVAL._usage_tokens(None) is None


def test_paired_summary_reports_real_deltas_without_requiring_a_positive_result():
    manifest = json.loads((ROOT / "evals" / "cold_start" / "click.json").read_text())
    results = [
        {
            "task": "shell-completion-dispatch",
            "rep": 1,
            "condition": "baseline",
            "code": 0,
            "observed_model_tokens": 1000,
            "exploration_calls": 4,
            "total_tool_calls": 4,
            "seconds": 20.0,
            "total_cost_usd": 0.02,
            "found_correct_file": True,
            "answer_mentions_target": True,
            "openreflex_context_delivered": False,
        },
        {
            "task": "shell-completion-dispatch",
            "rep": 1,
            "condition": "primed",
            "code": 0,
            "observed_model_tokens": 1200,
            "exploration_calls": 5,
            "total_tool_calls": 5,
            "seconds": 24.0,
            "total_cost_usd": 0.024,
            "found_correct_file": True,
            "answer_mentions_target": True,
            "openreflex_context_delivered": True,
        },
    ]
    summary = LIVE_EVAL._paired_summary(results, manifest, "claude-sonnet-4-6")
    assert summary["pairs_valid"] == 1
    assert summary["paired_relative_change"]["observed_model_tokens"] == 0.2
    assert summary["paired_relative_change"]["total_tool_calls"] == 0.25
    assert summary["missing_treatment_context"] == []
    assert "pilot only" in summary["claim_scope"]
