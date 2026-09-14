"""The engine: lifecycle events become local execution memory and explainable decisions."""

import math
import re
import time
from collections import Counter
from pathlib import Path

from . import control, detect, learning
from .decision import DecisionSnapshot, make_snapshot, render_recap, render_trace, render_why
from .models import CandidatePath, Context, Execution, Experience, Lesson, Outcome, Status, Task, ToolCall, uid
from .policy import load_policy
from .privacy import PROGRESS, categorize, error_signature, file_paths, fingerprint, redact
from .routing import Budget, Limits, budget_for, candidates, classify, embed, limits_from_env, similarity
from .store import Store, database_path

FOLLOW_UP = re.compile(r"^\s*(yes|no|ok(ay)?|thanks|thank you|continue|go on|go ahead|proceed|sure|lgtm|do it|"
                       r"looks good|try again|retry|again|next|y|n)\b", re.IGNORECASE)
UNTRACKED = "(task started without a captured prompt)"


def is_substantial(prompt: str) -> bool:
    text = prompt.strip()
    if not text or text.startswith("/"):
        return False
    words = re.findall(r"\w+", text)
    if len(words) < 5:
        return False
    return not (len(words) < 10 and FOLLOW_UP.match(text))


class Engine:
    def __init__(self, project: Path, store: Store | None = None, clock=time.time):
        self.project = project
        self.store = store or Store(database_path(project))
        self.clock = clock
        self.policy = load_policy(project)

    def close(self):
        self.store.close()

    # ------------------------------------------------------------------ lifecycle events

    def prompt(self, agent: str, session: str, prompt: str, can_inject: bool = True) -> str | None:
        now = self.clock()
        with self.store.transaction():
            current = self.store.latest(agent, session)
            if current is not None and not is_substantial(prompt):
                self._reopen(current)
                return None
            if current is not None and now - current.started_at < self.policy.number("engine.duplicate_prompt_window_seconds") and \
                    self._task(current).description == redact(prompt, 1000):
                return None
            if current is not None and self._task(current).description == UNTRACKED and current.ended_at is None:
                context = self._describe(current, prompt, now)
                execution = current
            else:
                if current is not None and current.ended_at is None:
                    self._finalize(current)
                execution, context = self._start(agent, session, prompt, now, substantial=is_substantial(prompt))
            execution.pending_context = context.injected and not can_inject
            self.store.put(execution)
        return context.text if context.injected and can_inject else None

    def take_pending_context(self, agent: str, session: str) -> str | None:
        with self.store.transaction():
            execution = self.store.active(agent, session)
            if execution is None or not execution.pending_context:
                return None
            execution.pending_context = False
            self.store.put(execution)
            context = next(iter(self.store.list("Context", "task_id", execution.task_id, limit=1)), None)
            return context.text if context is not None and context.injected else None

    def take_notice(self, agent: str, session: str) -> str | None:
        """Return the newest visible recap/intervention once, advancing past ambient snapshots too."""
        with self.store.transaction():
            execution = self.store.latest(agent, session)
            if execution is None or execution.visible_decisions >= len(execution.decision_history):
                return None
            pending = execution.decision_history[execution.visible_decisions:]
            previous = DecisionSnapshot.from_dict(execution.decision_history[execution.visible_decisions - 1]) \
                if execution.visible_decisions else None
            execution.visible_decisions = len(execution.decision_history)
            self.store.put(execution)
            visible = [DecisionSnapshot.from_dict(item) for item in pending if item.get("visibility") != "ambient"]
            if not visible:
                return None
            return render_recap(visible[-1], previous)

    def tool_start(self, agent: str, session: str, tool_id: str | None, name: str, arguments: object) -> str | None:
        now = self.clock()
        with self.store.transaction():
            execution = self._execution_for(agent, session, now)
            fp = fingerprint(name, arguments)
            if tool_id and self._find_call(execution.id, tool_id, fp, running_only=False) is not None:
                return None
            call = ToolCall(execution_id=execution.id, external_id=tool_id or f"fp:{fp[:16]}:{now:.3f}", name=name[:100],
                            category=categorize(name, arguments), fingerprint=fp,
                            files=file_paths(arguments, self.project), started_at=now)
            self.store.put(call)
            self.store.link(execution.id, "used", call.id)
            return self._retry_warning(execution, call)

    def tool_end(self, agent: str, session: str, tool_id: str | None, name: str, arguments: object,
                 success: bool, error: str | None = None, output_chars: int = 0) -> str | None:
        now = self.clock()
        with self.store.transaction():
            execution = self._execution_for(agent, session, now)
            fp = fingerprint(name, arguments)
            call = self._find_call(execution.id, tool_id, fp, running_only=not tool_id)
            if call is None:
                call = ToolCall(execution_id=execution.id, external_id=tool_id or f"fp:{fp[:16]}:{now:.3f}",
                                name=name[:100], category=categorize(name, arguments), fingerprint=fp,
                                files=file_paths(arguments, self.project), started_at=now)
            elif call.status != "running":
                return None
            divisor = self.policy.number("context.chars_per_token")
            tokens = max(0, round(int(output_chars) / divisor))
            call.ended_at, call.status = now, "success" if success else "failure"
            call.duration_ms = round((now - call.started_at) * 1000, 1)
            call.output_tokens_estimate = tokens
            call.error_signature = None if success else (error_signature(error) or f"{call.category} failed")
            self.store.put(call)
            self.store.link(execution.id, "used", call.id)
            execution.output_tokens_estimate += tokens
            if success and call.category in PROGRESS:
                execution.last_progress_at = now
            calls = self._calls(execution.id)
            if not success:
                self.store.link(execution.id, "failed_with", call.id)
            else:
                for failed, resolver in learning.resolutions(calls):
                    self.store.link(failed.id, "resolved_by", resolver.id)
            message = self._alert(execution, calls, now)
            self.store.put(execution)
            return message

    def compaction(self, agent: str, session: str) -> None:
        with self.store.transaction():
            execution = self.store.active(agent, session)
            if execution is not None:
                execution.compactions += 1
                self.store.put(execution)

    def stop(self, agent: str, session: str) -> Outcome | None:
        with self.store.transaction():
            execution = self.store.active(agent, session)
            return self._finalize(execution) if execution is not None else None

    # ------------------------------------------------------------------ explicit agent-facing operations

    def current_execution(self, agent: str | None = None, session: str | None = None,
                          max_age: float | None = None):
        if agent and session:
            execution = self.store.latest(agent, session)
            if execution is not None:
                return execution
        now = self.clock()
        age = max_age if max_age is not None else self.policy.number("engine.recent_execution_max_age_seconds")
        limit = self.policy.integer("engine.recent_execution_limit")
        recent = [e for e in self.store.list("Execution", limit=limit) if now - e.started_at < age]
        return max(recent, key=lambda e: (e.ended_at is None, e.started_at), default=None)

    def context_for(self, description: str, agent: str = "mcp", session: str | None = None,
                    limits: Limits | None = None) -> tuple[Execution, Context]:
        now = self.clock()
        with self.store.transaction():
            current = self.current_execution(agent if session else None, session,
                                             max_age=self.policy.number("engine.mcp_current_max_age_seconds"))
            if current is not None and current.ended_at is None:
                task = self._task(current)
                if task.description == UNTRACKED or not task.substantial or limits is not None:
                    keep = task.description if task.description != UNTRACKED and task.substantial else description
                    self._describe(current, keep, now, limits)
                context = self.store.list("Context", "task_id", current.task_id, limit=1)[0]
                return current, context
            return self._start(agent, session or f"mcp-{int(now)}", description, now, substantial=True, limits=limits)

    def progress(self, agent: str | None = None, session: str | None = None):
        with self.store.transaction():
            execution = self.current_execution(agent if session else None, session)
            if execution is None:
                raise ValueError("No current execution; request an execution context first")
            calls, now = self._calls(execution.id), self.clock()
            budget, active = self._budget(execution), learning.active_seconds(execution, calls, now)
            problems = detect.detect(execution, calls, budget, now, active, self.policy)
            return execution, self._verdict(execution, calls, budget, active), problems, budget

    def choose_path(self, strategy: str, steps: list[str] | None = None,
                    execution_id: str | None = None) -> CandidatePath:
        with self.store.transaction():
            execution = self.store.get(execution_id) if execution_id else self.current_execution()
            if execution is None:
                raise ValueError("No current execution; request an execution context first")
            paths = self.store.list("CandidatePath", "task_id", execution.task_id)
            path = next((p for p in paths if p.strategy == strategy), None)
            if path is None:
                recommended = self.store.get(execution.recommended_path_id)
                path = recommended.model_copy(update={
                    "id": uid(), "strategy": redact(strategy, 60),
                    "steps": [redact(s, 200) for s in (steps or [])][:8], "evidence_count": 0, "uncertainty": 1.0})
                self.store.put(path)
            execution.chosen_path_id, execution.chosen_inferred = path.id, False
            limit = self._budget(execution) if execution.budget_source == "limit" else None
            configured = Limits(limit.seconds, limit.tool_calls, limit.context_tokens) if limit else limits_from_env()
            self._set_budget(execution, budget_for(path, configured, self.policy))
            self.store.put(execution)
            self.store.link(execution.id, "used", path.id)
            return path

    def record_outcome(self, status: Status, evidence: str, execution_id: str | None = None) -> Outcome:
        with self.store.transaction():
            execution = self.store.get(execution_id) if execution_id else self.current_execution()
            if execution is None:
                raise ValueError("No execution to record an outcome for")
            return self._finalize(execution, status=status, evidence=redact(evidence, 500), verified=True)

    def forget_experience(self, experience_id: str) -> dict[str, int]:
        """Delete one past task and everything learned from it; returns how many nodes of each kind were removed."""
        with self.store.transaction():
            experience = self.store.get(experience_id) if self.store.exists(experience_id) else None
            if not isinstance(experience, Experience):
                raise ValueError("Unknown experience id")
            removed: Counter = Counter()

            def drop(node) -> None:
                removed[type(node).__name__] += 1
                self.store.delete(node.id)

            for execution in self.store.list("Execution", "task_id", experience.task_id):
                for call in self.store.list("ToolCall", "execution_id", execution.id, limit=5000):
                    drop(call)
                for outcome in self.store.find("Outcome", execution_id=execution.id):
                    drop(outcome)
                for item in self.store.find("Experience", execution_id=execution.id):
                    for lesson in self.store.list("Lesson", "experience_id", item.id):
                        drop(lesson)
                    drop(item)
                self.store.forget_execution(execution.id)
                drop(execution)
            for kind in ("Context", "CandidatePath"):
                for node in self.store.list(kind, "task_id", experience.task_id):
                    drop(node)
            if self.store.exists(experience.task_id):
                drop(self.store.get(experience.task_id))
            return dict(removed)

    def preview(self, description: str) -> str:
        task = Task(description=redact(description, 1000), task_class=classify(description), session_id="preview",
                    agent="preview", started_at=self.clock())
        retrieved = self.retrieve(task.description, task.task_class)
        limits = limits_from_env()
        paths = candidates(task.id, task.task_class, self._evidence(task.task_class, task.description), limits,
                           self.policy)
        return render_context(task, paths, retrieved, self.lessons([x for x, _ in retrieved]),
                              budget_for(paths[0], limits, self.policy), self.policy)

    def decision_snapshots(self, execution_id: str | None = None) -> list[DecisionSnapshot]:
        """Snapshots of the given execution, or of the most recent one that made decisions. Activity without a
        captured prompt (a resumed session, a tool call before any prompt) must not hide the latest explanation."""
        if execution_id:
            execution = self.store.get(execution_id)
        else:
            decided = [e for e in self.store.list("Execution", limit=200) if e.decision_history]
            execution = max(decided, key=lambda e: e.started_at, default=None)
        if execution is None:
            return []
        return [DecisionSnapshot.from_dict(item) for item in execution.decision_history]

    def why(self, execution_id: str | None = None) -> str:
        snapshots = self.decision_snapshots(execution_id)
        if not snapshots:
            return "OPENREFLEX / WHY\n\nNo decision snapshot recorded yet."
        return render_why(snapshots[-1])

    def trace(self, execution_id: str | None = None) -> str:
        return render_trace(self.decision_snapshots(execution_id))

    def retrieve(self, description: str, task_class: str | None = None,
                 k: int | None = None) -> list[tuple[Experience, float]]:
        query = embed(description)
        now = self.clock()
        scored = []
        threshold = self.policy.number("retrieval.threshold")
        scan = self.policy.integer("engine.max_store_scan")
        for experience in self.store.list("Experience", limit=scan):
            sim = similarity(query, experience.embedding)
            if sim < threshold:
                continue
            age_weeks = max(0.0, now - experience.created_at) / (7 * 24 * 60 * 60)
            score = (sim
                     + (self.policy.number("retrieval.task_class_bonus") if experience.task_class == task_class else 0)
                     + (self.policy.number("retrieval.success_bonus") if experience.status == "success" else 0)
                     - min(self.policy.number("retrieval.age_bonus_limit"),
                           self.policy.number("retrieval.age_decay_per_week") * age_weeks))
            scored.append((experience, round(score, 4)))
        limit = k if k is not None else self.policy.integer("retrieval.max_experiences")
        return sorted(scored, key=lambda pair: -pair[1])[:limit]

    def lessons(self, experiences: list[Experience], limit: int | None = None) -> list[tuple[Lesson, float, int]]:
        grouped: dict[str, list[Lesson]] = {}
        for experience in experiences:
            for lesson in self.store.list("Lesson", "experience_id", experience.id):
                grouped.setdefault(lesson.key, []).append(lesson)
        ranked = []
        for items in grouped.values():
            combined = 1 - math.prod(1 - lesson.confidence for lesson in items)
            ranked.append((items[0], round(min(combined, 0.99), 3), len(items)))
        order = {"resolution": 0, "failure-loop": 1, "strategy": 2, "context": 3, "repetition": 4, "files": 5}
        count = limit if limit is not None else self.policy.integer("context.max_lessons")
        return sorted(ranked, key=lambda r: (-r[1], order.get(r[0].kind, 9)))[:count]

    # ------------------------------------------------------------------ internals

    def _task(self, execution: Execution) -> Task:
        return self.store.get(execution.task_id)

    def _calls(self, execution_id: str) -> list[ToolCall]:
        return sorted(self.store.list("ToolCall", "execution_id", execution_id,
                                      limit=self.policy.integer("engine.max_store_scan")),
                      key=lambda c: (c.started_at, c.id))

    def _find_call(self, execution_id: str, tool_id: str | None, fp: str, running_only: bool) -> ToolCall | None:
        if tool_id:
            return next(iter(self.store.find("ToolCall", limit=1, execution_id=execution_id, external_id=tool_id)), None)
        matches = [c for c in self.store.find("ToolCall", execution_id=execution_id, fingerprint=fp)
                   if c.status == "running" or not running_only]
        return max(matches, key=lambda c: c.started_at, default=None)

    def _execution_for(self, agent: str, session: str, now: float) -> Execution:
        execution = self.store.latest(agent, session)
        if execution is None:
            execution, _ = self._start(agent, session, UNTRACKED, now, substantial=False)
        self._reopen(execution)
        return execution

    def _reopen(self, execution: Execution) -> None:
        if execution.ended_at is not None:
            execution.ended_at = None
            self.store.put(execution)

    def _evidence(self, task_class: str, description: str, exclude: str | None = None) -> list[Experience]:
        query = embed(description)
        scan = self.policy.integer("engine.max_store_scan")
        same = [e for e in self.store.list("Experience", "task_class", task_class, limit=scan)
                if e.execution_id != exclude and e.description != UNTRACKED]
        threshold = self.policy.number("retrieval.threshold")
        similar = [e for e in same if similarity(query, e.embedding) >= threshold]
        minimum = self.policy.integer("retrieval.minimum_similar_evidence")
        return similar if len(similar) >= minimum else same

    def _start(self, agent: str, session: str, description: str, now: float,
               substantial: bool, limits: Limits | None = None) -> tuple[Execution, Context]:
        task = Task(description=redact(description, 1000), task_class=classify(description), session_id=session,
                    agent=agent, started_at=now, substantial=substantial)
        limits = limits or limits_from_env()
        paths = candidates(task.id, task.task_class, self._evidence(task.task_class, task.description), limits,
                           self.policy)
        execution = Execution(task_id=task.id, agent=agent, session_id=session, recommended_path_id=paths[0].id,
                              started_at=now, last_progress_at=now)
        self._set_budget(execution, budget_for(paths[0], limits, self.policy))
        self.store.put(task)
        for path in paths:
            self.store.put(path)
            self.store.link(path.id, "recommended_for", task.id)
        self.store.put(execution)
        self.store.link(task.id, "caused", execution.id)
        context = self._write_context(task, paths, self._budget(execution))
        self.store.link(execution.id, "used", context.id)
        execution.context_tokens = self._injected_context_tokens(context)
        if substantial:
            self._record_decision(execution, "start", "recommend", paths[0], paths, now,
                                  context_tokens=execution.context_tokens)
        self.store.put(execution)
        self.store.bind_session(agent, session, execution.id)
        return execution, context

    def _describe(self, execution: Execution, description: str, now: float, limits: Limits | None = None) -> Context:
        task = self._task(execution)
        task.description, task.task_class = redact(description, 1000), classify(description)
        task.substantial = is_substantial(description) or task.substantial
        self.store.put(task)
        for node in self.store.list("CandidatePath", "task_id", task.id) + self.store.list("Context", "task_id", task.id):
            self.store.delete(node.id)
        limits = limits or limits_from_env()
        paths = candidates(task.id, task.task_class, self._evidence(task.task_class, task.description), limits,
                           self.policy)
        for path in paths:
            self.store.put(path)
            self.store.link(path.id, "recommended_for", task.id)
        execution.recommended_path_id = paths[0].id
        execution.chosen_path_id, execution.chosen_inferred = None, False
        self._set_budget(execution, budget_for(paths[0], limits, self.policy))
        context = self._write_context(task, paths, self._budget(execution))
        execution.context_tokens = self._injected_context_tokens(context)
        if task.substantial:
            self._record_decision(execution, "start", "recommend", paths[0], paths, now,
                                  context_tokens=execution.context_tokens)
        self.store.put(execution)
        self.store.link(execution.id, "used", context.id)
        return context

    def _write_context(self, task: Task, paths: list[CandidatePath], budget: Budget | None = None) -> Context:
        retrieved = self.retrieve(task.description, task.task_class) if task.substantial else []
        experiences = [e for e, _ in retrieved]
        lessons = self.lessons(experiences)
        text = render_context(task, paths, retrieved, lessons, budget, self.policy)
        context = Context(task_id=task.id, text=text, experience_ids=[e.id for e in experiences],
                          lesson_ids=[lesson.id for lesson, _, _ in lessons],
                          injected=task.substantial and bool(experiences))
        self.store.put(context)
        for experience in experiences:
            self.store.link(context.id, "used", experience.id)
        if context.injected:
            for lesson, _, _ in lessons:
                self.store.link(lesson.id, "recommended_for", task.id)
        return context

    def _injected_context_tokens(self, context: Context) -> int:
        if not context.injected:
            return 0
        return round(len(context.text) / self.policy.number("context.chars_per_token"))

    def _record_decision(self, execution: Execution, phase: str, action: str, best: CandidatePath | None,
                         paths: list[CandidatePath], now: float, *, context_tokens: int = 0,
                         budget_used: float = 0.0, event: str = "", actual_tool_calls: int | None = None,
                         actual_tokens: int | None = None, elapsed_seconds: float | None = None,
                         outcome: str | None = None, expected_regret: float | None = None) -> DecisionSnapshot:
        task = self._task(execution)
        experiences = self.retrieve(task.description, task.task_class) if task.substantial else []
        snapshot = make_snapshot(now=now, phase=phase, action=action, best=best, paths=paths,
                                 experiences=experiences, policy=self.policy, context_tokens=context_tokens,
                                 budget_used=budget_used, event=event, actual_tool_calls=actual_tool_calls,
                                 actual_tokens=actual_tokens, elapsed_seconds=elapsed_seconds, outcome=outcome,
                                 expected_regret=expected_regret)
        if not task.substantial:
            # A greeting or a follow-up that only triggered a tool call is not a task; keep its snapshot quiet.
            snapshot = DecisionSnapshot.from_dict({**snapshot.as_dict(), "visibility": "ambient"})
        execution.decision_history.append(snapshot.as_dict())
        self.store.put(execution)
        return snapshot

    def _retry_warning(self, execution: Execution, call: ToolCall) -> str | None:
        same = sorted((c for c in self.store.find("ToolCall", execution_id=execution.id, fingerprint=call.fingerprint)
                       if c.id != call.id), key=lambda c: c.started_at)
        failures = [c for c in same if c.status == "failure"]
        marker = "retry:" + call.fingerprint[:12]
        threshold = self.policy.integer("detectors.repeat_threshold") - 1
        if len(failures) >= threshold and not any(c.status == "success" for c in same) and marker not in execution.alerts:
            execution.alerts.append(marker)
            self.store.put(execution)
            signature = failures[-1].error_signature or "an error"
            return (f"OpenReflex: this exact {call.name} call already failed {len(failures)}x with "
                    f"\"{signature}\". Change the input or approach before retrying.")
        return None

    def _set_budget(self, execution: Execution, budget: Budget) -> None:
        execution.budget_seconds, execution.budget_tool_calls = round(budget.seconds, 1), round(budget.tool_calls, 1)
        execution.budget_tokens, execution.budget_source = round(budget.context_tokens), budget.source

    def _budget(self, execution: Execution) -> Budget:
        if execution.budget_tool_calls is not None:
            return Budget(execution.budget_seconds, execution.budget_tool_calls, execution.budget_tokens,
                          execution.budget_source or "estimated")
        recommended = self.store.get(execution.recommended_path_id) if self.store.exists(execution.recommended_path_id) else None
        if recommended:
            return budget_for(recommended, policy=self.policy)
        values = self.policy.table("routing.budget")
        return Budget(float(values["minimum_seconds"]), float(values["minimum_tool_calls"]),
                      float(values["minimum_context_tokens"]), "estimated")

    def _verdict(self, execution: Execution, calls: list[ToolCall], budget: Budget, active: float) -> control.Verdict:
        paths = self.store.list("CandidatePath", "task_id", execution.task_id)
        by_strategy = {p.strategy: p for p in paths}
        history = control.pivots(execution)
        declared = self.store.get(execution.chosen_path_id) if execution.chosen_path_id and not execution.chosen_inferred \
            and self.store.exists(execution.chosen_path_id) else None
        recommended = next((p for p in paths if p.id == execution.recommended_path_id), None)
        inferred = learning.infer_strategy(calls) or ("test-first" if any(c.category == "test" for c in calls) else "")
        current = (by_strategy.get(history[-1][1]) if history else None) or declared or by_strategy.get(inferred) or recommended
        tried = {name for source, target, _ in history for name in (source, target)}
        since = max(execution.last_progress_at, control.switch_time(execution, calls))
        return control.assess(execution, calls, current, paths, budget, active, since, tried, self.policy)

    def _alert(self, execution: Execution, calls: list[ToolCall], now: float) -> str | None:
        if now - execution.last_alert_at < self.policy.number("detectors.cooldown_seconds"):
            return None
        budget, active = self._budget(execution), learning.active_seconds(execution, calls, now)
        problems = detect.detect(execution, calls, budget, now, active, self.policy)
        if not problems:
            return None
        verdict = self._verdict(execution, calls, budget, active)
        key = {"pivot": f"pivot:{verdict.current or 'unplanned'}>{verdict.alternative.strategy}" if verdict.alternative else None,
               "stop": "stop"}.get(verdict.action)
        fresh_verdict = key is not None and key not in {v.rpartition("@")[0] for v in execution.verdicts}
        alert = detect.select(execution, problems, now, self.policy)
        if alert is None and not fresh_verdict:
            return None
        if alert is not None:
            execution.alerts.append(alert.kind)
        alert = alert or max(problems, key=lambda a: a.severity)
        execution.last_alert_at = now
        execution.verdicts.append(f"{key or verdict.action}@{len(calls)}")
        advice = {
            "failure_loop": "Don't retry the same fix: re-read the error and question the assumption behind it",
            "repeated_action": "Reuse the earlier result instead of re-running the same call",
            "stagnation": "Progress has stalled; re-plan before continuing",
            "context_growth": "Prefer targeted reads (line ranges, filtered or tail'ed command output) over full dumps",
            "over_budget": "This is past the execution budget; re-scope or re-plan",
        }[alert.kind]
        parts = [f"OpenReflex: {alert.detail}."]
        if verdict.action == "stop":
            parts.append(f"Recommendation: stop. More work is unlikely to pay off ({verdict.summary()}). "
                         "Summarize what was tried and what failed, and ask the user how to proceed.")
        elif verdict.action == "pivot":
            path = verdict.alternative
            parts.append(f"{advice}. Recommendation: pivot to {path.strategy} - {' -> '.join(path.steps)} "
                         f"({verdict.summary()}).")
        else:
            parts.append(f"{advice}. Recommendation: continue on this path ({verdict.summary()}).")
        signature = next((c.error_signature for c in reversed(calls) if c.status == "failure"), None)
        if signature and alert.kind == "failure_loop":
            known = [item for item in self.store.list("Lesson", "kind", "resolution",
                                                     limit=self.policy.integer("engine.max_store_scan"))
                     if signature in item.text]
            if known:
                parts.append(f"Previously: {known[0].text}")

        paths = self.store.list("CandidatePath", "task_id", execution.task_id)
        by_strategy = {path.strategy: path for path in paths}
        best = verdict.alternative if verdict.action == "pivot" else by_strategy.get(verdict.current or "")
        best = best or next((path for path in paths if path.id == execution.recommended_path_id), None)
        event = verdict.action if verdict.action in {"pivot", "stop"} else alert.kind
        self._record_decision(execution, "runtime", verdict.action, best, paths, now,
                              context_tokens=execution.context_tokens or 0, budget_used=verdict.budget_used,
                              event=event)
        return " ".join(parts)

    def _finalize(self, execution: Execution, status: Status | None = None, evidence: str | None = None,
                  verified: bool = False) -> Outcome:
        now = self.clock()
        calls = self._calls(execution.id)
        stale = self.policy.number("engine.stale_running_call_seconds")
        for call in calls:
            if call.status == "running" and now - call.started_at > stale:
                call.status, call.ended_at, call.error_signature = "failure", call.started_at, "no completion observed"
                self.store.put(call)
        execution.ended_at = execution.ended_at or now
        task = self._task(execution)
        outcome_id = "out-" + execution.id
        existing = self.store.get(outcome_id) if self.store.exists(outcome_id) else None
        if status is None:
            if existing is not None and existing.verified:
                status, evidence, verified = existing.status, existing.evidence, True
            else:
                status, evidence = learning.infer_status(calls)
        paths = self.store.list("CandidatePath", "task_id", task.id)
        chosen = self.store.get(execution.chosen_path_id) if execution.chosen_path_id and not execution.chosen_inferred else None
        if chosen is None:
            strategy = learning.infer_strategy(calls)
            chosen = next((p for p in paths if p.strategy == strategy), None)
            execution.chosen_path_id, execution.chosen_inferred = (chosen.id if chosen else None), True
        outcome = Outcome(id=outcome_id, execution_id=execution.id, status=status, evidence=evidence or "",
                          verified=verified, elapsed_seconds=round(learning.active_seconds(execution, calls, now), 1),
                          tool_calls=len(calls), failures=sum(c.status == "failure" for c in calls),
                          output_tokens_estimate=execution.output_tokens_estimate,
                          chosen_strategy=chosen.strategy if chosen else None)
        alternatives = candidates(task.id, task.task_class,
                                  self._evidence(task.task_class, task.description, execution.id), policy=self.policy)
        outcome.estimated_regret, outcome.best_alternative, outcome.regret_basis = learning.regret(outcome, chosen, alternatives)
        self.store.put(outcome)
        self.store.link(execution.id, "caused", outcome.id)
        if chosen is not None:
            self.store.link(execution.id, "used", chosen.id)

        if not any(item.get("phase") == "complete" for item in execution.decision_history):
            budget = self._budget(execution)
            used = budget.usage(outcome.elapsed_seconds, outcome.tool_calls, outcome.output_tokens_estimate)
            self._record_decision(execution, "complete", "complete", chosen or (paths[0] if paths else None), paths,
                                  now, context_tokens=execution.context_tokens or 0, budget_used=used,
                                  event="complete", actual_tool_calls=outcome.tool_calls,
                                  actual_tokens=outcome.output_tokens_estimate, elapsed_seconds=outcome.elapsed_seconds,
                                  outcome=outcome.status, expected_regret=outcome.estimated_regret)
        self.store.put(execution)

        if not calls:
            return outcome

        context = next(iter(self.store.list("Context", "task_id", task.id, limit=1)), None)
        edited = Counter(f for c in calls if c.category == "edit" and c.status == "success" for f in c.files)
        touched = Counter(f for c in calls for f in c.files)
        files = [f for f, _ in edited.most_common(10)] + [f for f, _ in touched.most_common(20) if f not in edited]
        experience = Experience(
            id="exp-" + execution.id, task_id=task.id, execution_id=execution.id, outcome_id=outcome.id,
            agent=execution.agent, description=task.description, task_class=task.task_class,
            strategy=outcome.chosen_strategy, status=status, elapsed_seconds=outcome.elapsed_seconds,
            tool_calls=outcome.tool_calls, output_tokens_estimate=outcome.output_tokens_estimate, files=files[:20],
            benefited=bool(context and context.experience_ids), estimated_regret=outcome.estimated_regret,
            alerts=[a for a in execution.alerts if not a.startswith("retry:")], verdicts=list(execution.verdicts),
            embedding=embed(task.description), created_at=now)
        self.store.put(experience)
        self.store.link(outcome.id, "caused", experience.id)
        for old in self.store.list("Lesson", "experience_id", experience.id):
            self.store.delete(old.id)
        pairs = learning.resolutions(calls)
        for failed, resolver in pairs:
            self.store.link(failed.id, "resolved_by", resolver.id)
        for lesson in learning.extract_lessons(experience, calls, pairs, execution.alerts):
            self.store.put(lesson)
            self.store.link(experience.id, "caused", lesson.id)
        return outcome


def render_context(task: Task, paths: list[CandidatePath], retrieved: list[tuple[Experience, float]],
                   lessons: list[tuple[Lesson, float, int]], budget: Budget | None = None, policy=None) -> str:
    cfg = policy or load_policy()
    experiences = [e for e, _ in retrieved]
    succeeded = sum(e.status == "success" for e in experiences)
    best, rest = paths[0], paths[1:]
    lines = [f"[OpenReflex] {task.task_class} task | {len(experiences)} similar past task(s) here, {succeeded} succeeded."]
    basis = f"from {best.evidence_count} past run(s)" if best.evidence_count else "default prior"
    lines.append(f"Suggested path: {best.strategy} - {' -> '.join(best.steps)} "
                 f"(success~{best.success_probability:.0%}, ~{best.tool_calls:.0f} tool calls, {basis}).")
    if rest:
        def label(p: CandidatePath) -> str:
            if p.dominated_by:
                return f"{p.strategy} (dominated by {p.dominated_by})"
            return f"{p.strategy} ({'over your limit' if not p.within_limits else f'{p.score:+.2f} vs {best.score:+.2f}'})"
        lines.append("Alternatives: " + ", ".join(label(p) for p in rest))
    if budget is not None:
        lines.append(f"Budget: ~{budget.tool_calls:.0f} tool calls, ~{budget.seconds / 60:.0f} min, "
                     f"~{budget.context_tokens / 1000:.0f}k tokens of tool output"
                     + (" (your limit)." if budget.source == "limit" else "."))
    max_files = cfg.integer("context.max_likely_files")
    files = Counter(f for e in experiences if e.status == "success" for f in e.files[:max_files])
    if files:
        lines.append("Likely relevant files: " + ", ".join(f for f, _ in files.most_common(max_files)))
    shown = [item for item in lessons if item[0].kind != "files"]
    if shown:
        lines.append("Lessons:")
        lines += [f"- {lesson.text}" + (f" (seen {support}x)" if support > 1 else "") for lesson, _, support in shown]
    lines.append("Advisory only. If you follow a different approach, the choose_path tool records it.")
    text = "\n".join(lines)
    max_chars = cfg.integer("context.max_chars")
    return text if len(text) <= max_chars else text[: max_chars - 1] + "..."
