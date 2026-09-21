"""Typed response contracts for machine-readable OpenReflex MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReflexScoreResult(BaseModel):
    available: bool = Field(description="Whether a decision snapshot is available for the most recent decided task.")
    reason: str | None = Field(default=None, description="Why no score is available, when available is false.")
    reflex_score: int | None = Field(default=None, ge=0, le=100,
                                     description="Strength of the recommendation on a 0-100 scale; not success probability.")
    success_probability: float | None = Field(default=None, ge=0, le=1,
                                              description="Estimated probability of success for the recommended strategy.")
    decision_confidence: float | None = Field(default=None, ge=0, le=1,
                                              description="Confidence in the recommendation from the available evidence.")
    strategy: str | None = Field(default=None, description="Recommended strategy for the latest decision.")
    next_best_strategy: str | None = Field(default=None, description="Highest-ranked alternative strategy, if any.")
    route_advantage: float | None = Field(default=None, ge=0, le=1,
                                          description="Normalised advantage of the recommended route over the next best route.")
    evidence_count: int | None = Field(default=None, ge=0,
                                       description="Number of relevant prior experiences supporting the decision.")
    context_tokens: int | None = Field(default=None, ge=0,
                                       description="Estimated tokens injected from prior experience for this task.")
    budget_used: float | None = Field(default=None, ge=0,
                                      description="Largest fraction of the task budget consumed across time, calls and context.")
    signals: dict[str, float] = Field(default_factory=dict,
                                      description="Normalised component signals used to compute the Reflex Score.")
    policy_version: str | None = Field(default=None, description="OpenReflex decision-policy version used for the score.")


class ExperienceSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(description="Experience Graph id for the past task.")
    score: float = Field(description="Similarity/retrieval score for this query; higher ranks first.")
    description: str = Field(description="Redacted task description stored for the past execution.")
    class_name: str = Field(alias="class", serialization_alias="class", description="OpenReflex task class.")
    agent: str = Field(description="Agent that produced the experience.")
    strategy: str | None = Field(description="Strategy used for the past task when known.")
    status: str = Field(description="Observed outcome status: success, failure or unknown.")
    tool_calls: int = Field(ge=0, description="Number of captured tool calls in the execution.")
    minutes: float = Field(ge=0, description="Active execution time in minutes.")
    files: list[str] = Field(description="Project-relative files associated with the execution, capped for compactness.")


class LessonSummary(BaseModel):
    text: str = Field(description="A compact lesson extracted from one or more past executions.")
    confidence: float = Field(ge=0, le=1, description="Combined confidence in this lesson.")
    support: int = Field(ge=1, description="Number of experiences supporting the lesson.")


class SearchExperienceResult(BaseModel):
    experiences: list[ExperienceSummary] = Field(description="Matching past tasks ordered from best to worst match.")
    lessons: list[LessonSummary] = Field(description="Lessons derived from the returned experiences.")


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: Literal["Task", "Context", "CandidatePath", "Execution", "ToolCall", "Outcome", "Experience", "Lesson"] = \
        Field(description="Experience Graph node type.")
    id: str = Field(description="Stable node id within this project's local Experience Graph.")


class GraphEdge(BaseModel):
    source: str = Field(description="Source node id.")
    relation: Literal["used", "caused", "failed_with", "resolved_by", "recommended_for"] = \
        Field(description="Typed relationship between the source and target nodes.")
    target: str = Field(description="Target node id.")


class ExplainNodeResult(BaseModel):
    root: str = Field(description="Id of the graph node that was requested.")
    nodes: list[GraphNode] = Field(description="The root node and directly related nodes; embeddings are omitted.")
    edges: list[GraphEdge] = Field(description="Direct typed relationships to or from the root node.")


class ActivationMetrics(BaseModel):
    approved_at: float | None = Field(description="Unix timestamp when capture was approved for this project.")
    seconds_to_first_task: float | None = Field(description="Seconds from approval to the first captured task.")
    first_session_captured: bool | None = Field(description="Whether the first observed session produced an experience.")


class EngagementMetrics(BaseModel):
    tasks: int = Field(ge=0, description="Total captured tasks, including non-substantial tasks.")
    substantial_tasks: int = Field(ge=0, description="Tasks eligible for planning and experience retrieval.")
    executions: int = Field(ge=0, description="Total execution records.")
    experiences: int = Field(ge=0, description="Completed executions retained as reusable experiences.")
    active_weeks: int = Field(ge=0, description="Distinct weeks containing captured executions.")
    weeks_since_start: int = Field(ge=1, description="Weeks elapsed since activation or first task.")
    active_week_ratio: float | None = Field(description="Share of elapsed weeks containing activity.")
    agents: list[str] = Field(description="Agents observed in this project.")


class ExperienceReuseMetrics(BaseModel):
    reuse_rate: float | None = Field(description="Share of substantial tasks that received relevant prior experience; this measures coverage, not benefit.")
    benefit_rate: float | None = Field(description="Deprecated compatibility alias of reuse_rate; it does not measure causal benefit.")
    tasks_with_prior_experience: int = Field(ge=0, description="Number of substantial tasks that received prior experience.")


class OutcomeMetrics(BaseModel):
    known: int = Field(ge=0, description="Experiences whose outcome is success or failure rather than unknown.")
    verified: int = Field(ge=0, description="Outcomes explicitly verified by the agent or user.")
    success_rate: float | None = Field(description="Success rate among experiences with known outcomes.")


class EfficiencyProfile(BaseModel):
    n: int = Field(ge=0, description="Number of experiences in this observational group.")
    tool_calls: float | None = Field(description="Mean tool calls in the group.")
    model_tokens: float | None = Field(description="Mean real model-token usage when Claude telemetry is available.")
    tool_output_tokens_estimate: float | None = Field(description="Mean legacy estimate of tool-output tokens.")
    minutes: float | None = Field(description="Mean active execution time in minutes.")
    success_rate: float | None = Field(description="Success rate among known outcomes in the group.")
    known_outcomes: int = Field(ge=0, description="Number of known outcomes in the group.")


class EfficiencyObservational(BaseModel):
    with_prior_experience: EfficiencyProfile = Field(description="Observed metrics for tasks that reused prior experience.")
    without_prior_experience: EfficiencyProfile = Field(description="Observed metrics for tasks without prior experience.")
    tool_call_change: float | None = Field(description="Relative mean tool-call change; observational, not causal.")
    model_token_change: float | None = Field(description="Relative mean model-token change when real telemetry exists; observational, not causal.")
    time_change: float | None = Field(description="Relative mean active-time change; observational, not causal.")


class PathCheckMetrics(BaseModel):
    comparisons: int = Field(ge=0, description="Completed tasks with enough comparable past evidence to check another path.")
    better_option_found: int = Field(ge=0, description="Tasks where comparable past evidence indicated a better option.")
    by_class: dict[str, int] = Field(description="Number of evidence-backed path checks by task class.")


class RoutingMetrics(BaseModel):
    retrospective_best: dict[str, str] = Field(description="Best realised strategy per task class when enough evidence exists.")
    agreement: float | None = Field(description="Share of comparable executions where the recommendation matched retrospective best.")
    compared_executions: int = Field(ge=0, description="Number of executions eligible for routing-agreement comparison.")


class ExecutionControlMetrics(BaseModel):
    verdicts: dict[str, int] = Field(description="Counts of runtime continue, pivot and stop verdicts.")
    success_after_pivot_or_stop: float | None = Field(description="Observed success rate after pivot/stop advice; not causal.")
    tasks_within_tool_call_budget: float | None = Field(description="Share of measured tasks finishing within the tool-call budget.")


class ProjectReflexMetrics(BaseModel):
    visible: int = Field(ge=0, description="Learned and proven project-specific Reflex procedures currently available.")
    learned: int = Field(ge=0, description="Reflexes promoted after repeated successful project executions.")
    proven: int = Field(ge=0, description="Reflexes backed by stronger repeated and explicitly verified evidence.")


class ProjectInsightsResult(BaseModel):
    project: str = Field(description="Local project path represented by this Experience Graph.")
    activation: ActivationMetrics = Field(description="Activation and first-use metrics.")
    engagement: EngagementMetrics = Field(description="Capture and usage volume.")
    experience_reuse: ExperienceReuseMetrics = Field(description="How often prior experience was reused.")
    outcomes: OutcomeMetrics = Field(description="Known and verified outcome coverage.")
    efficiency_observational: EfficiencyObservational = Field(
        description="Observed efficiency with versus without reused experience; this is not a controlled comparison.")
    path_check: PathCheckMetrics = Field(description="Simple evidence-backed path comparison counts.")
    routing: RoutingMetrics = Field(description="Recommendation agreement with retrospective realised performance.")
    live_alerts: dict[str, int] = Field(description="Counts of loop, repetition, stagnation, context and budget alerts.")
    execution_control: ExecutionControlMetrics = Field(description="Runtime verdict and budget-adherence metrics.")
    project_reflexes: ProjectReflexMetrics = Field(description="Project-specific reusable procedures learned from execution evidence.")
    lessons: int = Field(ge=0, description="Number of extracted lessons retained in this project.")