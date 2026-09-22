import json

from openreflex.decision import render_recap
from openreflex.engine import Engine
from openreflex.hooks import handle, normalize
from openreflex.policy import load_policy
from openreflex.project import approve
from openreflex.routing import candidates, classify, task_mode
from openreflex.store import Store, database_path
from openreflex.usage import ingest_otlp_logs, register_session, usage_totals


def _attr(key, *, string=None, integer=None, double=None):
    value = {}
    if string is not None:
        value["stringValue"] = string
    elif integer is not None:
        value["intValue"] = str(integer)
    elif double is not None:
        value["doubleValue"] = double
    return {"key": key, "value": value}


def _otlp_api_request(session: str, *, request: str = "r1", input_tokens: int = 1000,
                      output_tokens: int = 200, cache_read: int = 300, cache_creation: int = 50,
                      cost: float = 0.0123):
    attrs = [
        _attr("event.name", string="claude_code.api_request"),
        _attr("session.id", string=session),
        _attr("prompt.id", string="p1"),
        _attr("request_id", string=request),
        _attr("model", string="claude-sonnet-5"),
        _attr("query_source", string="repl_main_thread"),
        _attr("input_tokens", integer=input_tokens),
        _attr("output_tokens", integer=output_tokens),
        _attr("cache_read_tokens", integer=cache_read),
        _attr("cache_creation_tokens", integer=cache_creation),
        _attr("cost_usd", double=cost),
    ]
    return {
        "resourceLogs": [{
            "resource": {"attributes": []},
            "scopeLogs": [{"logRecords": [{"timeUnixNano": "1789722000000000000", "attributes": attrs}]}],
        }]
    }


def test_task_modes_have_separate_paths():
    assert classify("Research and explain the repository architecture end to end") == "investigate"
    assert classify("Compare these deployment options and recommend an approach") == "think"
    assert task_mode("debug") == "build"
    policy = load_policy()
    investigate = candidates("i", "investigate", [], policy=policy, task_mode_name="investigate")
    think = candidates("t", "think", [], policy=policy, task_mode_name="think")
    build = candidates("b", "debug", [], policy=policy, task_mode_name="build")
    assert {p.strategy for p in investigate} == {"source-first", "cross-check", "broad-then-deep"}
    assert {p.strategy for p in think} == {"reason-first", "compare-options", "evidence-first"}
    assert {p.strategy for p in build} == {"inspect-first", "test-first", "incremental"}
    assert investigate[0].strategy == "source-first"
    assert think[0].strategy == "reason-first"


def test_reasoning_only_task_becomes_reusable_experience(project):
    engine = Engine(project)
    try:
        engine.prompt("claude-code", "think-1",
                      "Compare these deployment options and recommend which approach fits our constraints")
        outcome = engine.stop("claude-code", "think-1", assistant_completed=True)
        task = engine.store.get(engine.store.latest("claude-code", "think-1").task_id)
        experience = engine.store.get("exp-" + outcome.execution_id)
        assert task.task_mode == "think"
        assert outcome.status == "success"
        assert outcome.tool_calls == 0
        assert outcome.chosen_strategy == "reason-first"
        assert experience.task_mode == "think"
        assert experience.tool_calls == 0
    finally:
        engine.close()


def test_zero_tool_investigation_does_not_fake_recommended_path(project):
    engine = Engine(project)
    try:
        engine.prompt("claude-code", "research-1",
                      "Research and explain the architecture of this repository and its module boundaries")
        outcome = engine.stop("claude-code", "research-1", assistant_completed=True)
        snapshots = engine.decision_snapshots(outcome.execution_id)
        experience = engine.store.get("exp-" + outcome.execution_id)
        assert outcome.status == "success"
        assert outcome.chosen_strategy is None
        assert experience.task_mode == "investigate"
        assert experience.strategy is None
        recap = render_recap(snapshots[-1])
        assert "VERIFIED" in recap
        assert "source-first" not in recap
        assert "tokens" not in recap
        assert "regret" not in recap.lower()
        assert "Path check" not in recap
    finally:
        engine.close()


def test_investigation_infers_cross_check_from_evidence_tools(project):
    engine = Engine(project)
    try:
        engine.prompt("claude-code", "research-2",
                      "Investigate the architecture and cross-check how configuration flows through the repository")
        for index, (tool, args) in enumerate([
            ("Read", {"file_path": "README.md"}),
            ("Grep", {"pattern": "config"}),
            ("Read", {"file_path": "CLAUDE.md"}),
            ("Grep", {"pattern": "module"}),
        ]):
            tool_id = f"r{index}"
            engine.tool_start("claude-code", "research-2", tool_id, tool, args)
            engine.tool_end("claude-code", "research-2", tool_id, tool, args, True, None, 100)
        outcome = engine.stop("claude-code", "research-2", assistant_completed=True)
        assert outcome.status == "success"
        assert outcome.chosen_strategy == "cross-check"
        assert all(path.strategy not in {"test-first", "incremental"}
                   for path in engine.store.list("CandidatePath", "task_id",
                                                 engine.store.latest("claude-code", "research-2").task_id))
    finally:
        engine.close()


def test_claude_stop_exposes_response_and_pending_work():
    event = normalize("claude-code", "Stop", {
        "session_id": "s",
        "last_assistant_message": "I have completed the analysis.",
        "background_tasks": [{"id": "b1"}],
        "session_crons": [{"id": "loop-1"}],
    })
    assert event.assistant_response_chars > 0
    assert event.pending_background == 1
    assert event.pending_crons == 1


def test_active_loop_reports_waiting_and_does_not_finalize(project, tmp_path, clock):
    approve(project)
    database = tmp_path / "waiting.sqlite3"

    def factory(root):
        return Engine(root, Store(database), clock=clock)

    base = {"session_id": "loop", "cwd": str(project)}
    handle("claude-code", "UserPromptSubmit",
           {**base, "prompt": "Investigate this deployment pipeline and report what is still changing"}, factory)
    output = handle("claude-code", "Stop", {
        **base,
        "last_assistant_message": "Initial pass complete.",
        "background_tasks": [],
        "session_crons": [{"id": "loop-1", "schedule": "30m"}],
    }, factory)
    data = json.loads(output)
    assert "WAITING" in data["systemMessage"]
    engine = factory(project)
    try:
        execution = engine.store.latest("claude-code", "loop")
        assert execution.ended_at is None
        assert engine.store.find("Outcome", execution_id=execution.id) == []
    finally:
        engine.close()


def test_waiting_execution_resumes_on_a_non_identical_next_prompt(project, tmp_path, clock):
    """A real /loop iteration rarely resends byte-identical text (timestamps, tick counters); the
    waiting execution must still resume rather than being silently finalized as unknown."""
    approve(project)
    database = tmp_path / "waiting.sqlite3"

    def factory(root):
        return Engine(root, Store(database), clock=clock)

    base = {"session_id": "loop", "cwd": str(project)}
    handle("claude-code", "UserPromptSubmit",
           {**base, "prompt": "Investigate this deployment pipeline and report what is still changing"}, factory)
    handle("claude-code", "Stop", {
        **base,
        "last_assistant_message": "Initial pass complete.",
        "background_tasks": [],
        "session_crons": [{"id": "loop-1", "schedule": "30m"}],
    }, factory)

    engine = factory(project)
    try:
        waiting = engine.store.latest("claude-code", "loop")
        assert waiting.waiting_for_future_work is True
    finally:
        engine.close()

    clock.advance(1800)
    handle("claude-code", "UserPromptSubmit",
           {**base, "prompt": "Investigate this deployment pipeline and report what is still changing (tick 2)"}, factory)

    engine = factory(project)
    try:
        resumed = engine.store.latest("claude-code", "loop")
        assert resumed.id == waiting.id
        assert resumed.ended_at is None
        assert resumed.waiting_for_future_work is False
        assert engine.store.find("Outcome", execution_id=waiting.id) == []
    finally:
        engine.close()


def test_trivial_zero_tool_response_is_not_recorded_as_success(project, tmp_path, clock):
    """A one-character final response should not count as a completed reasoning answer."""
    approve(project)
    database = tmp_path / "trivial.sqlite3"

    def factory(root):
        return Engine(root, Store(database), clock=clock)

    base = {"session_id": "think-1", "cwd": str(project)}
    handle("claude-code", "UserPromptSubmit",
           {**base, "prompt": "Why does the retry queue keep growing under load?"}, factory)
    handle("claude-code", "Stop", {**base, "last_assistant_message": "."}, factory)

    engine = factory(project)
    try:
        execution = engine.store.latest("claude-code", "think-1")
        outcome = engine.store.find("Outcome", execution_id=execution.id)[0]
        assert outcome.status != "success"
    finally:
        engine.close()


def test_otlp_token_usage_is_correlated_deduped_and_saved(project):
    session = "tokens-1"
    engine = Engine(project)
    try:
        engine.prompt("claude-code", session,
                      "Compare the current deployment options and recommend the safest migration approach")
        execution = engine.store.latest("claude-code", session)
    finally:
        engine.close()

    register_session(project, session)
    payload = _otlp_api_request(session)
    assert ingest_otlp_logs(payload) == 1
    assert ingest_otlp_logs(payload) == 0

    store = Store(database_path(project))
    try:
        totals = usage_totals(store, execution.id)
        assert totals["input"] == 1000
        assert totals["output"] == 200
        assert totals["cache_read"] == 300
        assert totals["cache_creation"] == 50
        assert totals["requests"] == 1
        assert totals["cost_usd"] == 0.0123
    finally:
        store.close()

    engine = Engine(project)
    try:
        outcome = engine.stop("claude-code", session, assistant_completed=True)
        assert outcome.model_tokens == 1550
        assert outcome.input_tokens == 1000
        experience = engine.store.get("exp-" + outcome.execution_id)
        assert experience.model_tokens == 1550
    finally:
        engine.close()


def test_completion_accounting_keeps_real_model_tokens_out_of_ambient_recap(project):
    engine = Engine(project)
    try:
        engine.prompt("claude-code", "recap",
                      "Compare our rollout options and recommend the most reversible migration strategy")
        register_session(project, "recap")
        ingest_otlp_logs(_otlp_api_request("recap", input_tokens=2200, output_tokens=800,
                                           cache_read=1000, cache_creation=0))
        outcome = engine.stop("claude-code", "recap", assistant_completed=True)
        snapshot = engine.decision_snapshots(outcome.execution_id)[-1]
        recap = render_recap(snapshot)
        assert outcome.model_tokens == 4000
        assert snapshot.model_tokens == 4000
        assert "model tokens" not in recap
        assert "tool-output est." not in recap
    finally:
        engine.close()
