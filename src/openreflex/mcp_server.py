"""MCP stdio server. Hooks do the ambient capture; these tools let an agent ask for and report on execution."""

import json
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import metrics
from .engine import Engine
from .project import approval, approve, project_root
from .routing import Limits

INSTRUCTIONS = """OpenReflex is local execution memory for this project. Hooks capture work automatically.
Use get_execution_context before a substantial task if no [OpenReflex] context was already provided.
Call choose_path if you deliberately take a different approach than suggested, check_progress when unsure
whether more work is paying off, and record_outcome once the result is verified (tests pass, user confirmed).
Never call approve_project unless the user asked for it."""


def build_server(project: Path) -> FastMCP:
    server = FastMCP("openreflex", instructions=INSTRUCTIONS, log_level="WARNING")

    def engine() -> Engine:
        if not approval(project):
            raise PermissionError(f"OpenReflex is not enabled for {project}. The user can run "
                                  "`openreflex approve` (or ask you to call approve_project).")
        return Engine(project)

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

    @server.tool()
    def get_execution_context(task: str, max_tool_calls: int | None = None, max_minutes: float | None = None,
                              max_context_tokens: int | None = None) -> str:
        """Retrieve relevant past experience for a task: candidate strategies scored on success, time, tool calls,
        context, risk, uncertainty and reversibility (dominated ones marked), an execution budget, likely files,
        and lessons. Call before substantial work when no [OpenReflex] context was injected. Optional max_* limits
        constrain the plan and budget."""
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

    @server.tool()
    def check_progress() -> str:
        """Estimate whether more work on the current path is still worth it: continue, pivot to another strategy,
        or stop and ask the user. Based on progress so far, failures and the execution budget. Records nothing."""
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

    @server.tool()
    def choose_path(strategy: str, steps: list[str] | None = None) -> str:
        """Declare the strategy you are following (a suggested one like 'test-first', or your own with steps).
        Improves regret analysis, which otherwise infers the path from tool activity."""
        return run(lambda e: f"Recorded chosen path: {e.choose_path(strategy, steps).strategy}")

    @server.tool()
    def record_outcome(status: Literal["success", "failure"], evidence: str) -> str:
        """Record the verified outcome of the current task, e.g. status='success', evidence='pytest -q passed'."""
        def operation(e: Engine):
            outcome = e.record_outcome(status, evidence)
            regret = "n/a" if outcome.estimated_regret is None else f"{outcome.estimated_regret:.3f}"
            return f"Outcome recorded: {outcome.status}. Execution regret {regret} ({outcome.regret_basis})."
        return run(operation)

    @server.tool()
    def search_experience(query: str, limit: int = 5) -> str:
        """Search past task experiences in this project by description similarity."""
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

    @server.tool()
    def explain_node(node_id: str) -> str:
        """Show an Experience Graph node and its direct relations (used, caused, failed_with, resolved_by,
        recommended_for). Embeddings are omitted."""
        def operation(e: Engine):
            graph = e.store.graph(node_id)
            for node in graph["nodes"]:
                node.pop("embedding", None)
            return json.dumps(graph, indent=2, default=str)
        return run(operation)

    @server.tool()
    def project_insights() -> str:
        """Capture health, experience reuse, efficiency, Execution Regret trend and routing agreement."""
        return run(lambda e: json.dumps(metrics.project_metrics(e, approval(project)), indent=2))

    @server.tool()
    def approve_project(confirm: bool = False) -> str:
        """Enable OpenReflex capture for this project. Only call when the user explicitly asked to enable it."""
        if not confirm:
            return "Not approved: pass confirm=true only after the user explicitly asked to enable OpenReflex."
        approve(project, source="mcp")
        return f"OpenReflex enabled for {project}."

    return server


def serve(project: str | None = None) -> None:
    build_server(project_root(project)).run("stdio")
