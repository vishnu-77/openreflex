"""Versioned, privacy-minimised execution state for future shadow learning.

This module is deliberately passive in vNext phase 0.1: it defines a reproducible state contract but is not wired into
routing, notices, prompts, or intervention behaviour. The next phase may capture these states in shadow mode.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass

from . import learning
from .models import Execution, ToolCall
from .privacy import VERIFICATION
from .routing import Budget

STATE_SCHEMA_VERSION = "execution-state.v1"

METRIC_SEMANTICS = {
    "active_seconds": "Execution time with long idle gaps capped using OpenReflex's existing active-time semantics.",
    "seconds_since_progress": "Wall-clock seconds since the last successful progress-producing tool call.",
    "tool_calls_total": "All observed tool calls for the execution, including running calls.",
    "tool_calls_completed": "Observed tool calls whose status is success or failure.",
    "tool_calls_failed": "Completed tool calls with failure status.",
    "output_tokens_estimate": "Existing local estimate of tool-output tokens; not model-provider billing tokens.",
    "context_tokens": "Tokens of OpenReflex context injected for the execution, or zero when none was injected.",
    "budget_pressure": "Maximum of time, tool-call and output-token budget ratios.",
    "verification_successes": "Successful test, lint or build calls observed so far.",
    "verification_failures": "Failed test, lint or build calls observed so far.",
    "successful_edits": "Successful tool calls categorised as edits.",
    "unique_files_touched": "Count of distinct project-relative file paths observed; paths themselves are excluded.",
    "distinct_failure_signatures": "Count of distinct minimised error signatures; signature text is excluded.",
    "max_failure_repeat": "Largest repeat count for any one minimised failure signature.",
}


@dataclass(frozen=True)
class ExecutionState:
    schema_version: str
    execution_id: str
    task_id: str
    captured_at: float
    phase: str
    active_seconds: float
    seconds_since_progress: float
    tool_calls_total: int
    tool_calls_completed: int
    tool_calls_failed: int
    tool_calls_running: int
    output_tokens_estimate: int
    context_tokens: int
    compactions: int
    category_counts: dict[str, int]
    verification_successes: int
    verification_failures: int
    successful_edits: int
    unique_files_touched: int
    distinct_failure_signatures: int
    max_failure_repeat: int
    budget_source: str
    time_budget_ratio: float
    tool_budget_ratio: float
    token_budget_ratio: float
    budget_pressure: float
    observation_fingerprint: str

    def as_dict(self) -> dict:
        return asdict(self)


def _ratio(value: float, limit: float) -> float:
    return round(max(0.0, value) / max(float(limit), 1e-9), 6)


def _fingerprint(observation: dict) -> str:
    encoded = json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def build_execution_state(
    execution: Execution,
    calls: list[ToolCall],
    budget: Budget,
    now: float,
    *,
    phase: str = "runtime",
    active_seconds: float | None = None,
) -> ExecutionState:
    """Build a deterministic learning state from telemetry OpenReflex already keeps locally.

    Raw prompts, transcripts, code, shell commands, tool names, file paths and error text are intentionally absent. The
    resulting structure is suitable for later shadow datasets without expanding OpenReflex's privacy boundary.
    """
    active = learning.active_seconds(execution, calls, now) if active_seconds is None else max(0.0, active_seconds)
    completed = [call for call in calls if call.status != "running"]
    failures = [call for call in completed if call.status == "failure"]
    categories = dict(sorted(Counter(call.category for call in calls).items()))
    verification = [call for call in completed if call.category in VERIFICATION]
    signatures = Counter(call.error_signature for call in failures if call.error_signature)
    files = {path for call in calls for path in call.files}

    time_ratio = _ratio(active, budget.seconds)
    tool_ratio = _ratio(len(calls), budget.tool_calls)
    token_ratio = _ratio(execution.output_tokens_estimate, budget.context_tokens)

    observation = {
        "phase": phase,
        "active_seconds": round(active, 3),
        "seconds_since_progress": round(max(0.0, now - execution.last_progress_at), 3),
        "tool_calls_total": len(calls),
        "tool_calls_completed": len(completed),
        "tool_calls_failed": len(failures),
        "tool_calls_running": sum(call.status == "running" for call in calls),
        "output_tokens_estimate": execution.output_tokens_estimate,
        "context_tokens": execution.context_tokens or 0,
        "compactions": execution.compactions,
        "category_counts": categories,
        "verification_successes": sum(call.status == "success" for call in verification),
        "verification_failures": sum(call.status == "failure" for call in verification),
        "successful_edits": sum(call.category == "edit" and call.status == "success" for call in completed),
        "unique_files_touched": len(files),
        "distinct_failure_signatures": len(signatures),
        "max_failure_repeat": max(signatures.values(), default=0),
        "budget_source": budget.source,
        "time_budget_ratio": time_ratio,
        "tool_budget_ratio": tool_ratio,
        "token_budget_ratio": token_ratio,
        "budget_pressure": max(time_ratio, tool_ratio, token_ratio),
    }

    return ExecutionState(
        schema_version=STATE_SCHEMA_VERSION,
        execution_id=execution.id,
        task_id=execution.task_id,
        captured_at=round(now, 6),
        observation_fingerprint=_fingerprint(observation),
        **observation,
    )
