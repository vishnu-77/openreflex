"""Experience Graph node types.

Plain dataclasses rather than pydantic: every hook is a short-lived process that runs on each tool call,
and pydantic's import plus model construction cost ~0.8s per invocation. Validation that matters (ranges,
enumerations, finiteness, unknown fields) is enforced explicitly in __post_init__.
"""

import dataclasses
import json
import math
from dataclasses import dataclass, field
from typing import Literal, get_args
from uuid import uuid4


def uid() -> str:
    return uuid4().hex


def unit(default: float | None = None):
    """A float constrained to [0, 1]."""
    extra = {} if default is None else {"default": default}
    return field(metadata={"range": (0.0, 1.0)}, **extra)


def non_negative(default: float | None = None):
    extra = {} if default is None else {"default": default}
    return field(metadata={"range": (0.0, math.inf)}, **extra)


def one_of(choices: tuple[str, ...], default: str | None = None):
    extra = {} if default is None else {"default": default}
    return field(metadata={"choices": choices}, **extra)


Status = Literal["success", "failure", "unknown"]
STATUSES = get_args(Status)


@dataclass(kw_only=True)
class Model:
    id: str = field(default_factory=uid)

    def __post_init__(self):
        for spec in dataclasses.fields(self):
            value = getattr(self, spec.name)
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{type(self).__name__}.{spec.name} must be finite")
            if "range" in spec.metadata:
                low, high = spec.metadata["range"]
                if not low <= value <= high:
                    raise ValueError(f"{type(self).__name__}.{spec.name}={value} outside [{low}, {high}]")
            if "choices" in spec.metadata and value not in spec.metadata["choices"]:
                raise ValueError(f"{type(self).__name__}.{spec.name}={value!r} not in {spec.metadata['choices']}")

    def model_dump(self) -> dict:
        return dataclasses.asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"), allow_nan=False)

    @classmethod
    def model_validate_json(cls, text: str):
        data = json.loads(text)
        known = {spec.name for spec in dataclasses.fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown {cls.__name__} fields: {sorted(unknown)}")
        return cls(**data)

    def model_copy(self, update: dict | None = None):
        return dataclasses.replace(self, **(update or {}))


@dataclass(kw_only=True)
class Task(Model):
    description: str
    task_class: str
    session_id: str
    agent: str
    started_at: float
    substantial: bool = True
    task_mode: str = one_of(("build", "investigate", "think"), "build")


@dataclass(kw_only=True)
class Context(Model):
    task_id: str
    text: str
    experience_ids: list[str] = field(default_factory=list)
    lesson_ids: list[str] = field(default_factory=list)
    injected: bool = False
    reflex_id: str | None = None
    embedding_version: str = "hash-lexical-v1"


@dataclass(kw_only=True)
class CandidatePath(Model):
    task_id: str
    strategy: str
    steps: list[str]
    success_probability: float = unit()
    time_seconds: float = non_negative()
    tool_calls: float = non_negative()
    context_tokens: float = non_negative()
    risk: float = unit()
    uncertainty: float = unit()
    reversibility: float = unit()
    expected_regret: float = non_negative(0.0)
    evidence_count: int = 0
    score: float = 0
    dominated_by: str | None = None
    within_limits: bool = True


@dataclass(kw_only=True)
class Execution(Model):
    task_id: str
    agent: str = "unknown"
    session_id: str = ""
    recommended_path_id: str
    chosen_path_id: str | None = None
    chosen_inferred: bool = False
    started_at: float
    ended_at: float | None = None
    context_tokens: int | None = None
    output_tokens_estimate: int = 0
    last_progress_at: float
    last_alert_at: float = 0
    alerts: list[str] = field(default_factory=list)
    compactions: int = 0
    pending_context: bool = False
    budget_seconds: float | None = None
    budget_tool_calls: float | None = None
    budget_tokens: float | None = None
    budget_source: str = ""
    verdicts: list[str] = field(default_factory=list)
    decision_history: list[dict] = field(default_factory=list)
    visible_decisions: int = 0
    waiting_for_future_work: bool = False
    reflex_id: str | None = None


@dataclass(kw_only=True)
class ToolCall(Model):
    execution_id: str
    external_id: str
    name: str
    category: str = "other"
    fingerprint: str
    files: list[str] = field(default_factory=list)
    started_at: float
    ended_at: float | None = None
    status: str = one_of(("running", "success", "failure"), "running")
    error: str | None = None
    error_signature: str | None = None
    duration_ms: float | None = None
    output_tokens_estimate: int = 0


@dataclass(kw_only=True)
class Outcome(Model):
    execution_id: str
    status: str = one_of(STATUSES)
    evidence: str
    verified: bool = False
    elapsed_seconds: float
    tool_calls: int
    failures: int
    output_tokens_estimate: int
    chosen_strategy: str | None = None
    best_alternative: str | None = None
    estimated_regret: float | None = None
    regret_basis: str = "unavailable: chosen path or verified outcome missing"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def model_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_creation_tokens


@dataclass(kw_only=True)
class Experience(Model):
    task_id: str
    execution_id: str
    outcome_id: str
    agent: str = "unknown"
    description: str
    task_class: str
    strategy: str | None
    status: str = one_of(STATUSES)
    elapsed_seconds: float
    tool_calls: int
    output_tokens_estimate: int
    files: list[str] = field(default_factory=list)
    benefited: bool = False
    estimated_regret: float | None = None
    alerts: list[str] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    embedding: list[float]
    created_at: float
    task_mode: str = one_of(("build", "investigate", "think"), "build")
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def model_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_creation_tokens


@dataclass(kw_only=True)
class UsageSample(Model):
    execution_id: str
    session_id: str
    prompt_id: str = ""
    request_id: str = ""
    model: str = ""
    query_source: str = "main"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float = 0.0
    observed_at: float = 0.0


@dataclass(kw_only=True)
class ProjectReflex(Model):
    """A project-scoped procedure compiled from repeated successful executions."""

    name: str
    family: str = ""
    task_mode: str = one_of(("build", "investigate", "think", "project"), "build")
    task_class: str
    state: str = one_of(("candidate", "learned", "proven", "stale"), "candidate")
    seed_strategy: str | None = None
    procedure: list[str] = field(default_factory=list)
    credit_graph: list[dict] = field(default_factory=list)
    credit_version: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    support_count: int = 0
    success_count: int = 0
    verified_count: int = 0
    confidence: float = unit(0.0)
    embedding: list[float] = field(default_factory=list)
    file_patterns: list[str] = field(default_factory=list)
    module_patterns: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass(kw_only=True)
class Lesson(Model):
    experience_id: str
    key: str
    kind: str
    task_class: str
    text: str
    confidence: float = unit()
    evidence_ids: list[str]


NODE_MODELS = {m.__name__: m for m in (Task, Context, CandidatePath, Execution, ToolCall, Outcome, Experience, Lesson)}
Relation = Literal["used", "caused", "failed_with", "resolved_by", "recommended_for"]
