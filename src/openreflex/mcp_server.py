"""MCP stdio server. Hooks do the ambient capture; these tools let an agent ask for and report on execution."""

import inspect
import json
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import metrics
from .engine import Engine
from .project import approval, approve, project_root
from .routing import Limits

INSTRUCTIONS = """OpenReflex is local execution memory for this project. Hooks capture work automatically.
Use get_execution_context before a substantial task if no [OpenReflex] context was already provided.
Call choose_path if you deliberately take a different approach than suggested, check_progress when unsure
whether more work is paying off, and record_outcome once the result is verified (tests pass, user confirmed).
Use explain_decision or get_execution_trace when the user asks why OpenReflex recommended something.
Never call approve_project unless the user asked for it."""

# Every tool works on local data only. Reads never change the Experience Graph; writes never delete from it.
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
PLAN = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
NOT_ENABLED = " Until the project is enabled, every tool except approve_project returns a 'not enabled' message."


def build_server(project: Path) -> FastMCP:
    server = FastMCP("openreflex", instructions=INSTRUCTIONS, log_level="WARNING")

    def engine() -> Engine:
        if not approval(project):
            raise PermissionError(f"OpenReflex is not enabled for {project}. The user can run "
                                  "`openreflex approve` (or ask you to call approve_project).")
        return Engine(project)

    def tool(title: str, annotations: ToolAnnotations, gated: bool = True):
        """Register a tool whose description is its docstring, plus the not-enabled note for gated tools."""
        def register(function):
            description = inspect.cleandoc(function.__doc__ or "") + (NOT_ENABLED if gated else "")
            return server.tool(title=title, description=description, annotations=annotations)(function)
        return register

    def run(operation):
        try:
            instance = engine()
        except PermissionError as error:
            return str(error)
        try:
            return operation(instance)
        except ValueError as error:
            return f"OpenReflex: {error}"
        finally:
            instance.close()

    @tool("Get execution context", PLAN)
    def get_execution_context(
        task: Annotated[str, Field(description="One or two plain sentences describing the task, e.g. 'Fix the login "
                                               "redirect loop after logout'. Secrets are redacted before storage.")],
        max_tool_calls: Annotated[int | None, Field(description="Optional upper limit on tool calls for this task. "
                                                                "Must be positive.")] = None,
        max_minutes: Annotated[float | None, Field(description="Optional upper limit on active working time, in "
                                                               "minutes. Must be positive.")] = None,
        max_context_tokens: Annotated[int | None, Field(description="Optional upper limit on tokens of tool output "
                                                                    "added to context. Must be positive.")] = None,
    ) -> str:
        """Plan a substantial task from this project's past experience. Returns plain text: similar past tasks, the
        suggested strategy with alternatives (dominated or over-limit ones marked), an execution budget, likely
        relevant files and lessons, followed by every candidate path's estimates and the execution id.

        Use it before a bug fix, feature, refactor or migration when no [OpenReflex] block was injected. Use
        search_experience instead to look up history without planning a task. Starts or re-plans the current task
        in the local graph; calling it again for the same task returns the same plan unless new limits are given."""
        def operation(e: Engine):
            given = [value for value in (max_tool_calls, max_minutes, max_context_tokens) if value is not None]
            if any(value <= 0 for value in given):
                raise ValueError("limits must be positive")
            limits = Limits(max_minutes * 60 if max_minutes else None, max_tool_calls, max_context_tokens) if given else None
            execution, context = e.context_for(task, limits=limits)
            paths = e.store.list("CandidatePath", "task_id", execution.task_id)
            order = [execution.recommended_path_id] + [p.id for p in sorted(paths, key=lambda p: -p.score)]
            paths = sorted(paths, key=lambda p: order.index(p.id))

            def status(p) -> str:
                return (f"dominated by {p.dominated_by}" if p.dominated_by else
                        "over the limits" if not p.within_limits else "Pareto-efficient")
            scored = "\n".join(
                f"- {p.strategy}: score {p.score:+.3f} ({status(p)}), success~{p.success_probability:.0%}, "
                f"~{p.tool_calls:.0f} calls, ~{p.time_seconds / 60:.0f} min, ~{p.context_tokens / 1000:.1f}k tokens, "
                f"risk {p.risk:.2f}, uncertainty {p.uncertainty:.2f}, reversibility {p.reversibility:.2f}, "
                f"expected regret {p.expected_regret:.3f}, evidence n={p.evidence_count}" for p in paths)
            return f"{context.text}\n\nCandidate paths:\n{scored}\n(execution {execution.id})"
        return run(operation)

    @tool("Check progress", READ)
    def check_progress() -> str:
        """Estimate whether more work on the current task's path is still worth it. Returns plain text starting with
        'Recommendation: continue', 'pivot' or 'stop', then the success estimates, the marginal value of each option,
        the execution budget and any detected problems (failure loops, stalled progress, budget overruns).

        Use it mid-task when unsure whether to keep going; follow a pivot by switching to the named strategy, and a
        stop by summarizing and asking the user. Reads the most recent task only and records nothing. Returns a
        message asking for get_execution_context first when no task exists."""
        def operation(e: Engine):
            execution, verdict, problems, budget = e.progress()
            action = verdict.action if problems else "continue"
            lines = [f"Recommendation: {action}" + ("" if problems else " (no signs of trouble)") + ".",
                     f"Estimate: {verdict.summary()}.",
                     f"Marginal value: continue {verdict.value_continue:+.3f}"
                     + (f", pivot to {verdict.alternative.strategy} {verdict.value_pivot:+.3f}" if verdict.alternative else "")
                     + ", stop +0.000.",
                     f"Budget: ~{budget.tool_calls:.0f} tool calls, ~{budget.seconds / 60:.0f} min, "
                     f"~{budget.context_tokens / 1000:.0f}k tokens of tool output ({budget.source})."]
            if problems:
                lines.append("Detected: " + "; ".join(p.detail for p in problems) + ".")
            if action == "pivot":
                lines.append(f"{verdict.alternative.strategy}: {' -> '.join(verdict.alternative.steps)}.")
            return "\n".join(lines) + f"\n(execution {execution.id})"
        return run(operation)

    @tool("Explain decision", READ)
    def explain_decision() -> str:
        """Explain the latest recommendation for the most recent task in plain text: the chosen route, Reflex Score
        and its component signals, confidence, evidence and the next-best route.

        Use it when the user asks why OpenReflex suggested a path, pivot or stop. Use get_reflex_score for the same
        numbers as JSON, and get_execution_trace for every decision in order. Records nothing."""
        return run(lambda e: e.why())

    @tool("Get execution trace", READ)
    def get_execution_trace() -> str:
        """Return the most recent task's decision timeline as plain text: one line per decision OpenReflex made, in
        order, with elapsed time, phase, action, strategy, Reflex Score and the triggering event. Never includes
        prompts, commands or tool output.

        Use it to review how a task unfolded; use explain_decision for only the latest decision. Records nothing."""
        return run(lambda e: e.trace())

    @tool("Get Reflex Score", READ)
    def get_reflex_score() -> str:
        """Return the latest decision's Reflex Score as JSON: reflex_score (0-100, the strength of the recommendation,
        not the chance of success), success_probability, decision_confidence, strategy, next_best_strategy,
        route_advantage, evidence_count, budget_used, component signals and policy_version. Returns
        {"available": false} before any decision exists.

        Use it when you need the numbers programmatically; use explain_decision for a readable explanation.
        Records nothing."""
        def operation(e: Engine):
            snapshots = e.decision_snapshots()
            if not snapshots:
                return json.dumps({"available": False, "reason": "no decision snapshot recorded yet"})
            snapshot = snapshots[-1]
            return json.dumps({
                "available": True,
                "reflex_score": snapshot.reflex_score,
                "success_probability": snapshot.success_probability,
                "decision_confidence": snapshot.decision_confidence,
                "strategy": snapshot.strategy,
                "next_best_strategy": snapshot.next_best_strategy,
                "route_advantage": snapshot.route_advantage,
                "evidence_count": snapshot.evidence_count,
                "context_tokens": snapshot.context_tokens,
                "budget_used": snapshot.budget_used,
                "signals": snapshot.score_components,
                "policy_version": snapshot.policy_version,
            }, indent=2)
        return run(operation)

    @tool("Choose path", WRITE)
    def choose_path(
        strategy: Annotated[str, Field(description="The strategy being followed: a suggested one ('inspect-first', "
                                                   "'test-first', 'incremental') or a short name for your own.")],
        steps: Annotated[list[str] | None, Field(description="For a custom strategy only: 2-4 short steps, e.g. "
                                                             "['Prototype the parser', 'Swap callers']. Ignored for "
                                                             "suggested strategies.")] = None,
    ) -> str:
        """Declare the strategy you are following for the most recent task, so the outcome and Execution Regret are
        compared against the right plan and the budget follows that path. Returns a one-line confirmation.

        Call it only when you deliberately depart from the suggested path; otherwise the path is inferred from tool
        activity. Calling it again replaces the earlier choice."""
        return run(lambda e: f"Recorded chosen path: {e.choose_path(strategy, steps).strategy}")

    @tool("Record outcome", WRITE)
    def record_outcome(
        status: Annotated[Literal["success", "failure"], Field(description="'success' once checks pass or the user "
                                                                           "confirms; 'failure' if the task failed "
                                                                           "or was abandoned.")],
        evidence: Annotated[str, Field(description="Short proof of the result, e.g. 'pytest tests/test_auth.py "
                                                   "passed' or 'user confirmed the fix'. Kept up to 500 characters.")],
    ) -> str:
        """Record the verified outcome of the most recent task, then learn from it: the experience, lessons and
        Execution Regret are updated. Returns a line with the status and the regret estimate.

        Call it once the result is verified; unverified work is otherwise inferred from tool activity, less
        reliably. Calling it again for the same task replaces the recorded outcome rather than adding another."""
        def operation(e: Engine):
            outcome = e.record_outcome(status, evidence)
            regret = "n/a" if outcome.estimated_regret is None else f"{outcome.estimated_regret:.3f}"
            return f"Outcome recorded: {outcome.status}. Execution regret {regret} ({outcome.regret_basis})."
        return run(operation)

    @tool("Search experience", READ)
    def search_experience(
        query: Annotated[str, Field(description="Words describing the topic, e.g. 'expired token login bug'. Matched "
                                                "lexically against past task descriptions.")],
        limit: Annotated[int, Field(description="Maximum number of past tasks to return, 1-20. Default 5.")] = 5,
    ) -> str:
        """Search this project's past tasks by description similarity. Returns JSON: 'experiences' (id, score,
        description, class, agent, strategy, status, tool_calls, minutes, files), best match first, and the
        'lessons' learned from them.

        Use it to answer "what did we learn / what worked before?" without starting a task; use
        get_execution_context to plan a new one. Pass an experience id to explain_node for its graph. Records
        nothing."""
        def operation(e: Engine):
            found = e.retrieve(query, k=max(1, min(limit, 20)))
            lessons = e.lessons([x for x, _ in found], limit=8)
            return json.dumps({
                "experiences": [{"id": x.id, "score": s, "description": x.description, "class": x.task_class,
                                 "agent": x.agent, "strategy": x.strategy, "status": x.status,
                                 "tool_calls": x.tool_calls, "minutes": round(x.elapsed_seconds / 60, 1),
                                 "files": x.files[:8]} for x, s in found],
                "lessons": [{"text": item.text, "confidence": c, "support": n} for item, c, n in lessons],
            }, indent=2)
        return run(operation)

    @tool("Explain graph node", READ)
    def explain_node(
        node_id: Annotated[str, Field(description="Id of an Experience Graph node, as returned by search_experience "
                                                  "(experience ids start with 'exp-') or get_execution_context "
                                                  "('execution <id>').")],
    ) -> str:
        """Show one Experience Graph node and its direct relations (used, caused, failed_with, resolved_by,
        recommended_for) as JSON with 'root', 'nodes' and 'edges'. Embeddings are omitted.

        Use it to trace why a lesson or path exists after finding an id with search_experience. Returns 'Unknown
        graph node' for an id that does not exist. Records nothing."""
        def operation(e: Engine):
            graph = e.store.graph(node_id)
            for node in graph["nodes"]:
                node.pop("embedding", None)
            return json.dumps(graph, indent=2, default=str)
        return run(operation)

    @tool("Project insights", READ)
    def project_insights() -> str:
        """Summarize what OpenReflex has recorded and learned in this project, as JSON: tasks and experiences
        captured, how often past experience was reused, known outcomes and success rate, observational efficiency
        with and without prior experience, the Execution Regret trend, routing agreement, alerts raised, verdicts
        (continue, pivot, stop) and lesson count.

        Use it when the user asks how OpenReflex is doing in this project; use search_experience for individual
        past tasks. Records nothing."""
        return run(lambda e: json.dumps(metrics.project_metrics(e, approval(project)), indent=2))

    @tool("Enable project", WRITE, gated=False)
    def approve_project(
        confirm: Annotated[bool, Field(description="Set to true only when the user has explicitly asked to enable "
                                                   "OpenReflex for this project. With false (the default) nothing "
                                                   "is changed.")] = False,
    ) -> str:
        """Enable OpenReflex capture for this project, so hooks start recording tasks locally. Returns a one-line
        confirmation. Enabling an already-enabled project changes nothing.

        Never call it on your own initiative: only when the user explicitly asks to enable OpenReflex. The user can
        disable it again with `openreflex revoke`."""
        if not confirm:
            return "Not approved: pass confirm=true only after the user explicitly asked to enable OpenReflex."
        approve(project, source="mcp")
        return f"OpenReflex enabled for {project}."

    return server


def serve(project: str | None = None) -> None:
    build_server(project_root(project)).run("stdio")
