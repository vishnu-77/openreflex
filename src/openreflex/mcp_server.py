"""MCP stdio server. Hooks do the ambient capture; these tools let an agent ask for and report on execution."""

import inspect
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import metrics
from .engine import Engine
from .mcp_contracts import (
    ExperienceSummary,
    ExplainNodeResult,
    LessonSummary,
    ProjectInsightsResult,
    ReflexScoreResult,
    SearchExperienceResult,
)
from .project import approval, approve, project_root
from .routing import Limits

INSTRUCTIONS = """OpenReflex is local execution memory for this project. Hooks capture work automatically.
Use get_execution_context before a substantial task if no [OpenReflex] context was already provided.
Call choose_path if you deliberately take a different approach than suggested, check_progress when unsure
whether more work is paying off, and record_outcome once the result is confirmed. Research and reasoning tasks are
first-class: verification can be tests/builds, cross-checked evidence, or explicit user confirmation.
Use explain_decision or get_execution_trace when the user asks why OpenReflex recommended something.
Never call approve_project or forget_experience unless the user explicitly asked for it."""

# Every tool works on local data only. Reads never change the Experience Graph; writes never touch project files.
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
PLAN = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


def build_server(project: Path) -> FastMCP:
    server = FastMCP("openreflex", instructions=INSTRUCTIONS, log_level="WARNING")

    def engine() -> Engine:
        if not approval(project):
            raise PermissionError(f"OpenReflex is not enabled for {project}. The user can run "
                                  "`openreflex approve` (or ask you to call approve_project).")
        return Engine(project)

    def tool(title: str, annotations: ToolAnnotations):
        """Register a tool whose description is its docstring."""
        def register(function):
            return server.tool(title=title, description=inspect.cleandoc(function.__doc__ or ""),
                               annotations=annotations)(function)
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

    def run_structured(operation):
        """Structured tools fail as MCP errors instead of returning a string that violates outputSchema."""
        try:
            instance = engine()
        except PermissionError as error:
            raise RuntimeError(str(error)) from error
        try:
            return operation(instance)
        except ValueError as error:
            raise RuntimeError(f"OpenReflex: {error}") from error
        finally:
            instance.close()

    @tool("Get execution context", PLAN)
    def get_execution_context(
        task: Annotated[str, Field(min_length=1, max_length=1000,
                                   description="The task in one or two plain sentences, e.g. 'Fix the login redirect "
                                               "loop after logout'. Used to find similar past tasks; secrets are "
                                               "redacted before it is stored.")],
        max_tool_calls: Annotated[int | None, Field(gt=0, description="Optional cap on tool calls for this task; "
                                                                    "a positive integer. Default: no cap.")] = None,
        max_minutes: Annotated[float | None, Field(gt=0, description="Optional cap on active working time in minutes; "
                                                                  "a positive number. Default: no cap.")] = None,
        max_context_tokens: Annotated[int | None, Field(gt=0, description="Optional cap on tokens of tool output "
                                                                        "added to context; a positive integer. "
                                                                        "Default: no cap.")] = None,
    ) -> str:
        """Plan a task from this project's past experience.
        Returns: plain text: the [OpenReflex] context block (similar past tasks, the suggested path with alternatives,
        an execution budget where relevant, likely files/sources, and lessons), then each candidate path's estimates
        and how much comparable past evidence exists.
        Use when: starting any substantial coding, investigation, research, analysis, review, planning or reasoning task
        and no [OpenReflex] block was injected.
        Not for: looking up history (use search_experience) or checking progress mid-task (use check_progress).
        Side effects: starts or re-plans the current task in the local Experience Graph; touches no project files,
        runs no commands, sends nothing over the network. Calling it again for the same task returns the same plan
        unless new limits are given.
        Errors: invalid non-positive limits are rejected by the input schema; a 'not enabled' message is returned
        until the project is approved."""
        def operation(e: Engine):
            given = [value for value in (max_tool_calls, max_minutes, max_context_tokens) if value is not None]
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
                f"past evidence n={p.evidence_count}" for p in paths)
            return f"{context.text}\n\nCandidate paths:\n{scored}\n(execution {execution.id})"
        return run(operation)

    @tool("Check progress", READ)
    def check_progress() -> str:
        """Estimate whether more work on the current task's path is still worth it.
        Returns: plain text starting with 'Recommendation: continue', 'pivot' or 'stop', then the success estimates
        for the current path and the best alternative, the marginal value of each option, the execution budget and
        how much of it is used, and any detected problems (failure loop, repeated calls, stalled progress, context
        growth, budget overrun).
        Use when: unsure mid-task whether to keep going. Follow 'pivot' by switching to the named strategy; follow
        'stop' by summarizing what was tried and asking the user.
        Not for: planning a task (use get_execution_context).
        Side effects: none; read-only on the most recent task.
        Errors: asks for get_execution_context first when no task exists; a 'not enabled' message until the project
        is approved."""
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
        """Explain OpenReflex's latest recommendation for the most recent task.
        Returns: plain text with the recommended strategy, the Reflex Score (0-100: how strong the recommendation
        is, not the chance of success), the estimated success probability, confidence, the signals behind the
        score, the next-best strategy with its route advantage, and the policy version.
        Use when: the user asks why OpenReflex suggested a path, pivot or stop.
        Not for: the same numbers as structured data (use get_reflex_score) or every decision in order (use
        get_execution_trace).
        Side effects: none; read-only.
        Errors: 'No decision snapshot recorded yet' before any task was planned; a 'not enabled' message until the
        project is approved."""
        return run(lambda e: e.why())

    @tool("Get execution trace", READ)
    def get_execution_trace() -> str:
        """Return the decision timeline of the most recent task.
        Returns: plain text, one line per decision in order, with elapsed time, phase (start, runtime, complete),
        action, strategy, Reflex Score and the event that triggered it. Never includes prompts, commands or tool
        output.
        Use when: reviewing how a task unfolded.
        Not for: only the latest decision (use explain_decision).
        Side effects: none; read-only.
        Errors: 'No decision snapshots recorded yet' before any task was planned; a 'not enabled' message until the
        project is approved."""
        return run(lambda e: e.trace())

    @tool("Get candidate paths", READ)
    def get_candidate_paths() -> str:
        """Show every candidate path OpenReflex considered for the most recent task side by side.
        Returns: plain text with each strategy's score, success probability, cost/risk numbers, and whether it
        was dominated; which path was recommended; and which one was actually followed - explicit (via
        choose_path), inferred from tool-call evidence, or not yet determined while the execution is still
        running.
        Use when: the user asks what other approaches were considered, or whether the agent followed the
        suggested path.
        Not for: a single recommendation's reasoning (use explain_decision) or the decision timeline (use
        get_execution_trace).
        Side effects: none; read-only.
        Errors: 'No execution recorded yet' before any task was planned; a 'not enabled' message until the
        project is approved."""
        return run(lambda e: e.paths())

    @tool("Get Reflex Score", READ)
    def get_reflex_score() -> ReflexScoreResult:
        """Return the latest decision's Reflex Score and machine-readable components.
        Returns: structured fields for availability, Reflex Score (0-100 recommendation strength, not success
        probability), success probability, confidence, strategy, next-best strategy, route advantage, evidence,
        context cost, budget use, component signals and policy version. If no decision exists, available=false and
        reason explains why.
        Use when: a program or agent needs decision numbers it can inspect without parsing prose.
        Not for: a readable explanation (use explain_decision) or the full decision timeline (use get_execution_trace).
        Side effects: none; read-only.
        Errors: an MCP error is returned until the project is approved."""
        def operation(e: Engine):
            snapshots = e.decision_snapshots()
            if not snapshots:
                return ReflexScoreResult(available=False, reason="no decision snapshot recorded yet")
            snapshot = snapshots[-1]
            return ReflexScoreResult(
                available=True,
                reflex_score=snapshot.reflex_score,
                success_probability=snapshot.success_probability,
                decision_confidence=snapshot.decision_confidence,
                strategy=snapshot.strategy,
                next_best_strategy=snapshot.next_best_strategy,
                route_advantage=snapshot.route_advantage,
                evidence_count=snapshot.evidence_count,
                context_tokens=snapshot.context_tokens,
                budget_used=snapshot.budget_used,
                signals=snapshot.score_components,
                policy_version=snapshot.policy_version,
            )
        return run_structured(operation)

    @tool("Choose path", WRITE)
    def choose_path(
        strategy: Annotated[str, Field(min_length=1, max_length=60,
                                       description="The strategy being followed: one of the suggested names "
                                                   "'inspect-first', 'test-first' or 'incremental', or a short "
                                                   "kebab-case name for your own, e.g. 'spike-then-rewrite'.")],
        steps: Annotated[list[str] | None, Field(description="For a custom strategy only: 2-4 short steps, e.g. "
                                                             "['Prototype the toml loader', 'Swap the callers']. "
                                                             "Ignored for suggested strategies.")] = None,
    ) -> str:
        """Declare the strategy you are following for the most recent task.
        Returns: one line, 'Recorded chosen path: <strategy>'.
        Use when: deliberately departing from the suggested path, so OpenReflex remembers what was actually done
        rather than confusing the recommendation with the observed work.
        Not for: tasks that follow the suggestion; the path is then inferred from tool activity.
        Side effects: writes the choice to the local Experience Graph; calling it again replaces the earlier choice.
        Touches no project files.
        Errors: 'No current execution' before any task was planned (call get_execution_context first); a 'not
        enabled' message until the project is approved."""
        return run(lambda e: f"Recorded chosen path: {e.choose_path(strategy, steps).strategy}")

    @tool("Record outcome", WRITE)
    def record_outcome(
        status: Annotated[Literal["success", "failure"], Field(description="'success' when the result is confirmed "
                                                                           "(tests/builds passed, research was cross-checked, "
                                                                           "or the user confirmed it); 'failure' when the "
                                                                           "task failed or was abandoned.")],
        evidence: Annotated[str, Field(min_length=1, max_length=500,
                                       description="Short proof of the result, e.g. 'pytest tests/test_auth.py "
                                                   "passed' or 'user confirmed the fix'. Secrets are redacted.")],
    ) -> str:
        """Record the verified outcome of the most recent task and learn from it.
        Returns: the recorded status plus a plain-language Path check. A better path is only named when comparable
        completed tasks provide evidence; otherwise the result says that no better option is proven.
        Use when: the result is confirmed: tests/lint/build passed, research was cross-checked against relevant
        evidence, the user confirmed the answer, or the task failed/was abandoned.
        Not for: declaring the strategy (use choose_path).
        Side effects: finalizes the task in the local Experience Graph and updates its experience, lessons and
        path comparison; calling it again for the same task replaces the recorded outcome. Touches no project files.
        Errors: 'No execution to record an outcome for' before any task was planned; a 'not enabled' message until
        the project is approved."""
        def operation(e: Engine):
            outcome = e.record_outcome(status, evidence)
            path_check = (f"better option: {outcome.best_alternative} (supported by comparable past tasks)"
                          if outcome.best_alternative else "better option: none proven")
            return f"Outcome recorded: {outcome.status}. Path check: {path_check}."
        return run(operation)

    @tool("Search experience", READ)
    def search_experience(
        query: Annotated[str, Field(min_length=1, max_length=1000,
                                    description="Words describing the topic, e.g. 'expired token login bug'. "
                                                "Matched lexically against past task descriptions.")],
        limit: Annotated[int, Field(ge=1, le=20,
                                    description="Maximum number of past tasks to return. Default 5; allowed 1-20.")] = 5,
    ) -> SearchExperienceResult:
        """Search this project's past tasks by description similarity.
        Returns: structured 'experiences' (id, score, description, class, agent, strategy, status, tool_calls,
        minutes, files), best match first, plus structured 'lessons' (text, confidence, support). Both lists are empty
        when nothing is similar enough.
        Use when: the user asks what was learned or what worked before, or to find an experience id for
        explain_node or forget_experience.
        Not for: planning a new task (use get_execution_context).
        Side effects: none; read-only. Matching is lexical, on task descriptions only.
        Errors: invalid limit values are rejected by the input schema; an MCP error is returned until the project is
        approved."""
        def operation(e: Engine):
            found = e.retrieve(query, k=limit)
            lessons = e.lessons([x for x, _ in found], limit=8)
            return SearchExperienceResult(
                experiences=[ExperienceSummary(id=x.id, score=s, description=x.description, class_name=x.task_class,
                                               agent=x.agent, strategy=x.strategy, status=x.status,
                                               tool_calls=x.tool_calls, minutes=round(x.elapsed_seconds / 60, 1),
                                               files=x.files[:8]) for x, s in found],
                lessons=[LessonSummary(text=item.text, confidence=c, support=n) for item, c, n in lessons],
            )
        return run_structured(operation)

    @tool("Explain graph node", READ)
    def explain_node(
        node_id: Annotated[str, Field(min_length=1, max_length=160,
                                      description="Id of an Experience Graph node: an experience id from "
                                                  "search_experience (starts with 'exp-'), the execution id from "
                                                  "get_execution_context, or any node id from an earlier "
                                                  "explain_node result.")],
    ) -> ExplainNodeResult:
        """Show one Experience Graph node with its direct relations.
        Returns: structured 'root', 'nodes' (Task, Execution, ToolCall, Outcome, Experience, Lesson, Context or
        CandidatePath and their stored fields) and typed 'edges' (used, caused, failed_with, resolved_by,
        recommended_for). Embeddings are omitted.
        Use when: tracing why a lesson or recommendation exists, after finding an id with search_experience or
        get_execution_context.
        Not for: searching by topic (use search_experience).
        Side effects: none; read-only.
        Errors: an MCP error reports 'Unknown graph node' for an id that does not exist, and an MCP error is returned
        until the project is approved."""
        def operation(e: Engine):
            graph = e.store.graph(node_id)
            for node in graph["nodes"]:
                node.pop("embedding", None)
            return ExplainNodeResult.model_validate(graph)
        return run_structured(operation)

    @tool("Get project insights", READ)
    def get_project_insights() -> ProjectInsightsResult:
        """Summarize what OpenReflex has recorded and learned in this project.
        Returns: structured activation, engagement, experience reuse, outcomes, observational efficiency with and
        without prior experience, path-comparison trends, routing agreement, live alerts, execution-control metrics
        and lesson count. Efficiency comparisons are observational and are not presented as causal evidence.
        Use when: the user asks how OpenReflex is doing in this project or a program needs project-level metrics.
        Not for: individual past tasks (use search_experience).
        Side effects: none; read-only.
        Errors: an MCP error is returned until the project is approved."""
        return run_structured(lambda e: ProjectInsightsResult.model_validate(metrics.project_metrics(e, approval(project))))

    @tool("Enable project", WRITE)
    def approve_project(
        confirm: Annotated[bool, Field(description="true only when the user has explicitly asked to enable "
                                                   "OpenReflex for this project; with false (the default) nothing "
                                                   "changes.")] = False,
    ) -> str:
        """Enable OpenReflex capture for this project.
        Returns: one line confirming the project is enabled, or 'Not approved' when confirm is false.
        Use when: the user explicitly asks to enable OpenReflex here. Never call it on your own initiative; the user
        can also run `openreflex approve`, and `openreflex revoke` disables capture again.
        Not for: anything else; every other tool answers with a 'not enabled' message until this has happened.
        Side effects: writes the project's approval to the local OpenReflex home; enabling an already enabled
        project changes nothing. Touches no project files.
        Errors: none."""
        if not confirm:
            return "Not approved: pass confirm=true only after the user explicitly asked to enable OpenReflex."
        approve(project, source="mcp")
        return f"OpenReflex enabled for {project}."

    @tool("Forget experience", DELETE)
    def forget_experience(
        experience_id: Annotated[str, Field(min_length=5, max_length=160, pattern=r"^exp-",
                                             description="The experience id to delete, as returned by "
                                                         "search_experience; starts with 'exp-'.")],
        confirm: Annotated[bool, Field(description="true only when the user has explicitly asked to forget this "
                                                   "task; with false (the default) nothing is deleted.")] = False,
    ) -> str:
        """Delete one past task from this project's memory.
        Returns: one line listing what was removed (task, executions, tool calls, outcomes, experience, lessons), or
        'Not forgotten' when confirm is false.
        Use when: the user explicitly asks to forget a specific past task, for example one that involved sensitive
        work or taught a wrong lesson. Never call it on your own initiative.
        Not for: deleting everything; the user runs `openreflex forget --yes` for that.
        Side effects: permanently removes that task's nodes from the local Experience Graph; other tasks are
        untouched. Touches no project files.
        Errors: 'Unknown experience id' for an id that does not exist, is not an experience, or was already
        forgotten; a 'not enabled' message until the project is approved."""
        if not confirm:
            return "Not forgotten: pass confirm=true only after the user explicitly asked to forget this task."
        def operation(e: Engine):
            removed = e.forget_experience(experience_id)
            detail = ", ".join(f"{count} {kind}" for kind, count in sorted(removed.items()))
            return f"Forgotten: {detail} removed from this project's memory."
        return run(operation)

    return server


def serve(project: str | None = None) -> None:
    build_server(project_root(project)).run("stdio")