# OpenReflex

**Muscle memory for AI coding agents.**

[![CI](https://github.com/vishnu-77/openreflex/actions/workflows/ci.yml/badge.svg)](https://github.com/vishnu-77/openreflex/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/openreflex)](https://pypi.org/project/openreflex/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Ambient execution intelligence for AI coding agents. Install it once and keep working normally. It records how
each task actually went (strategy, tool calls, failures, what fixed them, which files mattered). Before the next
similar task it hands the agent a short **Execution Context**. While a task runs, it steps in only when the
evidence says re-planning is worthwhile.

Everything runs locally in SQLite. There is no service, no account, and no network access.

```
install once  ->  work normally  ->  OpenReflex learns continuously
```

## Install (under 2 minutes)

```bash
pipx install openreflex          # or: uv tool install openreflex   (puts `openreflex` on PATH)
cd your-project
openreflex install claude-code   # or codex | cursor | opencode; also enables the project
```

`install` writes project-level hook and MCP config for one agent, merging with any existing files, and approves
the project. Use `--dry-run` to preview the changes.

### Plugin install (no project files)

| Agent | How |
|---|---|
| Claude Code | `claude plugin marketplace add vishnu-77/openreflex` then `claude plugin install openreflex@openreflex`, then `openreflex approve` in each project |
| Codex | `codex plugin marketplace add vishnu-77/openreflex` (reads `.agents/plugins/marketplace.json`), enable the plugin, trust its hooks once in `/hooks`, then `openreflex approve` |
| Cursor | copy `plugins/openreflex` to `~/.cursor/plugins/local/openreflex`, then `openreflex approve` |

Nothing is captured in a project until it is approved. An unapproved project shows a one-line notice at most
once a day. To stop capture, run `openreflex revoke`. To delete a project's data, run `openreflex forget --yes`.

## How it works

```
 agent hooks ──► openreflex hook <agent> <event> ──► Engine ──► Experience Graph (SQLite)
   prompt        normalize payload per agent               │
   tool start    (hooks.py)                                ├─ before: retrieve experience, score 3 candidate
   tool end                                                │          paths, render Execution Context
   compaction                                              ├─ during: detect failure loops, repeated calls,
   stop                                                    │          stagnation, context growth, over-budget
                                                           └─ after:  infer outcome + chosen path, estimate
 agent ◄── additionalContext / alerts ◄────────────────────           Execution Regret, extract lessons
 agent ──► MCP tools (get_execution_context, choose_path, record_outcome, search_experience, ...)
```

**Experience Graph.** The nodes are `Task`, `Context`, `CandidatePath`, `Execution`, `ToolCall`, `Outcome`,
`Experience`, and `Lesson`. They are connected by `used`, `caused`, `failed_with`, `resolved_by`, and
`recommended_for`:

```
Task -caused-> Execution -used-> Context -used-> Experience
CandidatePath -recommended_for-> Task            Lesson -recommended_for-> Task
Execution -failed_with-> ToolCall -resolved_by-> ToolCall (the edit that fixed it)
Execution -caused-> Outcome -caused-> Experience -caused-> Lesson
```

**Before a task.** A prompt counts as substantial if it has at least 5 words and isn't a follow-up like "yes,
continue". For those prompts, OpenReflex:
1. Retrieves similar past experiences.
2. Scores `inspect-first`, `test-first`, and `incremental` on success probability, time, tool calls, context
   cost, risk, uncertainty, and reversibility. Each score is a Beta-style blend of a prior and observed outcomes.
3. Injects a context of at most 1,400 characters: the suggested path, alternatives, likely relevant files, and
   lessons.

Nothing is injected when there is no relevant experience, so a new project costs zero context tokens.

**During a task.** Each alert kind fires at most once per execution, with a 3-minute cooldown. Stagnation is
only judged after implementation has started, so exploratory reading does not trigger it. An alert names a
concrete alternative path and any known fix for the current error.

**After a task.** The `Stop` hook finalizes the execution. Later turns reopen it and finalize it again, so the
same task keeps one experience. Outcome and chosen path come from `record_outcome`/`choose_path` when the agent
calls them. Otherwise they are inferred: only a check that passed or failed after the last edit counts as
evidence. **Execution Regret** is the best alternative's expected utility minus the chosen path's realized
utility. It is withheld (not guessed) when the outcome is unknown.

## Agent integrations

| | Prompt context | Tool capture | Failure signal | Alerts delivered via | Turn end |
|---|---|---|---|---|---|
| Claude Code | `UserPromptSubmit` additionalContext | Pre/PostToolUse | `PostToolUseFailure` | PostToolUse additionalContext | `Stop` |
| Codex | `UserPromptSubmit` additionalContext | Pre/PostToolUse | parsed from `tool_response` | PostToolUse additionalContext | `Stop` |
| Cursor | deferred to first `postToolUse`* | pre/postToolUse | `postToolUseFailure` | postToolUse `additional_context` | `stop` |
| OpenCode | system-prompt transform (plugin) | tool.execute.before/after | `message.part.updated` error | appended to tool output | `session.idle` |

\* Cursor's `beforeSubmitPrompt` cannot inject context, so the context is held until the first tool result.
Cursor can also run Claude Code hook configs. Those calls are attributed to Cursor and de-duplicated.

**Claude Code is verified in live sessions** (see [Testing](#testing)). The Codex, Cursor, and OpenCode adapters
follow each agent's documented hook protocol (checked September 2026) and are tested with protocol-shaped and
fuzzed payloads, but have not yet run inside live sessions of those agents.

A hook always exits 0 and never blocks. Errors go to `~/.openreflex/logs/errors.log`, which
`openreflex doctor` shows. Measured on Windows: median 381 ms per hook process, where bare Python startup
is about 255 ms. Sixteen parallel tool-call hooks were stored with no lost writes.

## Privacy

- Stored per tool call: tool name, a coarse category (`read`/`edit`/`search`/`test`/...), a SHA-256 fingerprint
  of the arguments, project-relative file paths, status, duration, output *size*, and a masked one-line error
  signature. Paths outside the project, file contents, command text, tool output, and transcripts are never stored.
- Prompts are stored as task descriptions, at most 1,000 characters, with secrets (API keys, tokens, bearer
  headers, private keys) redacted.
- Data lives in `~/.openreflex/projects/<hash>/experience.sqlite3`. Set `OPENREFLEX_HOME` to relocate
  it, or `OPENREFLEX_DISABLE=1` to turn capture off everywhere.

## CLI

| Command | Purpose |
|---|---|
| `install <agent> [--dry-run]` | Write project hooks + MCP config and approve the project |
| `approve` / `revoke` | Enable / disable capture for the current project |
| `status [--json]` | Capture, reuse, outcome, efficiency, regret and routing metrics |
| `context "<task>"` | Preview the Execution Context a task would get |
| `doctor` | Installation checks and recent hook errors |
| `forget --yes` | Delete the project's data |
| `benchmark` | Simulated baseline-vs-guided benchmark |
| `hook <agent> <event>` / `mcp` | Used by agent configs |

## Measuring the success metrics

`openreflex status --json` reports these per project:

| Plan metric | Field |
|---|---|
| <2-minute activation | `activation.seconds_to_first_task` (approval → first captured task) |
| >70% first-session capture | `activation.first_session_captured` |
| >50% weekly active retention | `engagement.active_week_ratio` |
| >30% tasks benefiting | `experience_reuse.benefit_rate` |
| 20–30% fewer tool calls, 20% fewer tokens, 15% faster | `efficiency_observational.*_change` (observational only; confounded by task mix) |
| No success-rate regression | `outcomes.success_rate` |
| >70% routing agreement | `routing.agreement` vs. `routing.retrospective_best` |
| Declining regret | `execution_regret.by_class[*].early` vs `recent` |

Cross-project aggregation (retention across projects, fleet-level activation) belongs with M5 sync.

## Benchmark (simulated)

`openreflex benchmark` runs synthetic coding tasks from five task families, in two arms, through the real
engine. Both arms send real hook events and read back the real contexts and alerts; only the guided arm acts on
them. Default run: 150 tasks per arm × 3 seeds.

| Metric | Baseline | Guided | Change | Target |
|---|---|---|---|---|
| Tool calls / task | 13.97 | 9.21 | −34% | −20…−30% |
| Output tokens / task | 13,008 | 8,394 | −36% | −20% |
| Time / task | 349 s | 230 s | −34% | −15% |
| Success rate | 0.687 | 0.809 | +0.12 | ≥ baseline |
| Regret, first → last quarter | 0.107 → 0.103 | 0.079 → 0.036 | | declining |
| Routing agreement (2nd half) | – | 0.698 | | > 0.70 (**just missed**) |

**How to read this.** These are properties of the simulator, not evidence of real-world gains. Most of the
tool-call and token reduction comes from one assumption: a relevant-files hint cuts search and read calls from
6–9 down to 2–3. Time is modeled as calls × 25 s, so it moves exactly with calls. All assumptions are listed in
`SIMULATION_ASSUMPTIONS` in `benchmark.py` and written into the JSON report. What the benchmark does show: the
engine learns family-specific best strategies from noisy outcomes, regret declines, and alerts shorten failure
loops. Routing agreement falls short because candidate evidence is pooled per task class, so families in the
same class that prefer different strategies dilute each other.

## Status

| Milestone | State |
|---|---|
| **M1**: local engine, schemas, telemetry, MCP, agent integration | Done, for four agents |
| **M2**: retrieval, graph, Execution Context, cross-session memory | Done. Embeddings are offline lexical feature hashing, not a semantic model |
| **M3**: candidate paths, risk/reward scoring, live inefficiency detection | Done (deterministic) |
| **M4**: regret, lessons, cross-agent support, benchmark suite | Done. The benchmark is simulated; a real-task A/B harness is still to do |
| **M5**: learned Trajectory Router, cloud sync, team sharing | Not started |

Suggested next steps, in order:
1. Run the Codex, Cursor, and OpenCode integrations in live sessions and fix protocol drift.
2. Weight candidate evidence by similarity instead of pooling by task class; this is the cause of the routing-agreement miss.
3. Build a real-task A/B harness: the same task set with capture on and off.
4. Add a pluggable semantic embedder (keep lexical as the offline default) and a vector index once there are more than ~5k experiences.
5. M5.

## Testing

| Layer | What runs | Where |
|---|---|---|
| Unit + integration | Engine, adapters for all 4 agents, installers, CLI subprocesses, MCP, metrics, benchmark | CI: Linux, macOS, Windows × Python 3.11–3.13 |
| Stress | 24 parallel hook-process pairs (no lost writes), 3,000-experience retrieval, 400 fuzzed hostile payloads across all agents (only unparseable JSON may be rejected) | CI matrix |
| Packaging | Build sdist + wheel, `twine check --strict`, install the wheel into a clean venv, smoke-test console script, hooks, status and MCP over stdio | CI: Linux, macOS, Windows |
| Release | Publish to TestPyPI, then install from TestPyPI on 3 OSes and rerun the smoke test before PyPI | `release.yml` |
| Live agent | Real headless Claude Code sessions (`scripts/live_claude_code.py`) | Local; needs a signed-in `claude` |

The live Claude Code scenarios assert on the captured graph and on the session transcript, not on model wording:

1. **plugin-capture:** the plugin is loaded with `--plugin-dir`; a real bug fix is captured with categorized tool calls, an inferred success, and lessons.
2. **context-injection:** a similar task in a new session gets an Execution Context naming the right file, and the transcript shows the model received it.
3. **failure-loop-alert:** repeated failing test runs raise one alert, and the transcript shows it reached the model.
4. **mcp-tools:** the plugin's MCP server starts inside Claude Code and `search_experience` returns the captured files.
5. **project-install:** `openreflex install claude-code` works without the plugin.

## Development

```bash
pip install -e ".[dev]"
pytest                                   # unit, integration, stress
ruff check src tests scripts
python scripts/live_claude_code.py       # live Claude Code scenarios (real model calls, default haiku)
```

Layout: `engine.py` (event → graph), `routing.py` (retrieval features, candidates, utility), `detect.py` (live
alerts), `learning.py` (outcome/strategy inference, regret, lessons), `hooks.py` (agent adapters),
`mcp_server.py`, `install.py`, `metrics.py`, `benchmark.py`, `integrations/opencode.ts`, and
`plugins/openreflex` (Claude Code / Codex / Cursor plugin; its hook files are checked against `install.py`
by tests).
