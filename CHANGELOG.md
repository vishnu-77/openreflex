# Changelog

All notable changes to OpenReflex are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.3.1 (2026-09-14)

- **`project_insights` is now `get_project_insights`**, so every tool name is a verb followed by what it acts on.
- **New MCP tool `forget_experience`** deletes one past task from the project's memory (its task, execution, tool
  calls, outcome, experience and lessons). Like `approve_project`, it only acts with `confirm=true` after the user
  explicitly asks; `openreflex forget --yes` still deletes the whole project.
- MCP tool descriptions are restructured into labelled lines (what it returns, when to use it and when not to,
  side effects, errors), and every parameter states its format, constraints and default. Terms such as Execution
  Regret and Reflex Score are defined where they appear.

## 0.3.0 (2026-09-14)

Observable, configurable execution policy: every recommendation is recorded with its evidence and can be
explained, and the numbers behind routing and alerts live in a versioned policy file.

- **Decision snapshots and Reflex Score.** Each recommendation is stored with the chosen route, the next-best
  route, confidence, evidence, budget pressure and context overhead. The Reflex Score (0-100) describes how strong
  the recommendation is, separately from the estimated chance of success, and breaks down into component signals.
- **Explain decisions.** New `openreflex why` and `openreflex trace` commands, and new MCP tools
  `explain_decision`, `get_execution_trace` and `get_reflex_score`, read the same stored snapshots.
- **Recaps in Claude Code.** Short recaps appear when a task starts, when OpenReflex recommends a pivot or stop or
  detects trouble, and when the task completes, with the outcome, the path taken, observed cost and the regret
  comparison.
- **Versioned policy.** Routing, scoring, budget, detection and recap settings moved from code into a TOML policy.
  The packaged defaults can be overridden in `~/.openreflex/config.toml` and per project in `.openreflex.toml`.
- **Project identity.** Hook events resolve to the nearest repository (or `.openreflex.json` marker) from the
  event's working directory; `OPENREFLEX_PROJECT` still overrides it, and agent workspace variables are only a
  fallback. Hook traces record metadata only.
- **`openreflex uninstall <agent>`** removes OpenReflex's project hooks and MCP entries and keeps captured memory.
  `doctor` now reports how the project was resolved, plugin installs, and recent hook activity.
- **MCP tool descriptions.** Every tool now documents its parameters, return value, when to use it instead of its
  siblings, and whether it reads or writes, with MCP read-only and idempotency annotations.
- Recaps stay quiet for prompts that are not tasks, such as a greeting that only triggered a memory read.
- `docs/walkthrough.md` shows two real Claude Code sessions end to end, with the exact context the model received.

## 0.2.0 (2026-09-14)

Budget-aware execution: OpenReflex now chooses between paths on several objectives, gives each task a budget,
and recommends whether more work is worth it.

- **Pareto-efficient routing.** Candidate strategies are estimated on success, time, tool calls, context, risk,
  uncertainty, reversibility and expected regret. A strategy that another beats on every measure is marked
  dominated and never recommended or offered as a pivot.
- **Execution budget.** Each task gets a budget for tool calls, active time and context, with more headroom while
  estimates are uncertain. Optional limits come from `OPENREFLEX_BUDGET` (for example `calls=40,minutes=20`) or
  the new `max_tool_calls`, `max_minutes` and `max_context_tokens` arguments of `get_execution_context`; the
  recommended path is the best one that fits them.
- **Continue, pivot or stop.** When a detector finds trouble, OpenReflex updates the current path's success
  estimate from calls that made no progress or failed, weighs the value of the remaining work against the best
  untried alternative, and ends the alert with a recommendation. A stop recommendation asks the agent to
  summarize and hand back to the user.
- **New MCP tool `check_progress`** returns the same estimate on demand.
- **Regret and detours feed back into routing.** A strategy's recorded Execution Regret, and how often it ran
  into a failure loop, stalled progress or a budget overrun, now lower its ranking for similar tasks.
- `openreflex status` and `project_insights` report verdicts and how many tasks finished within their tool-call
  budget.
- An empty `OPENREFLEX_HOME` is treated as unset instead of the working directory.

## 0.1.3 (2026-09-14)

Codex CLI fixes found by running OpenReflex in live `codex exec` sessions (`scripts/live_codex.py`).

- Codex reports shell results without an exit status, so failed commands were recorded as successes. Failures are now read from the output of test, lint and build commands, and from shell errors such as an unknown command.
- Compound commands are categorized by the programs they run, so a file search whose arguments mention `pytest` is no longer counted as a test run.
- `openreflex install codex` forwards `OPENREFLEX_HOME` to the MCP server, which Codex starts with a filtered environment.
- Error signatures name the failing test instead of the test runner's closing tally, and ignore run durations, so repeated failures match and lessons read clearly.
- Releases also list the MCP server in the official MCP Registry (`server.json`), and `glama.json` names the maintainer for Glama.

## 0.1.2 (2026-09-14)

- The project website moved to [openreflex.cc](https://openreflex.cc); the package homepage and README links point there.

## 0.1.1 (2026-09-13)

- Rewrote the README around what OpenReflex does, how to install it for each agent, and how data is handled.
- Removed planning targets from the `openreflex benchmark` report and its JSON output.
- Added light and dark logo assets and a funding link.

## 0.1.0 (2026-09-13)

First public release.

- Lifecycle-hook integrations for Claude Code, OpenAI Codex CLI, Cursor and OpenCode, with `openreflex install <agent>` and a plugin for Claude Code and Codex.
- A local Experience Graph in SQLite that records tasks, tool calls, outcomes, experiences and lessons, without storing file contents, commands, tool output or transcripts.
- Execution Context injected before similar tasks: a suggested approach with alternatives, likely relevant files and lessons.
- Live alerts for failure loops, repeated identical calls, stalled progress and context growth.
- Outcome inference from checks that pass or fail after the last edit, Execution Regret, and lesson extraction.
- An MCP server with `get_execution_context`, `choose_path`, `record_outcome`, `search_experience`, `explain_node`, `project_insights` and `approve_project`.
- CLI commands: `install`, `approve`, `revoke`, `context`, `status`, `doctor`, `forget`, `benchmark`.
- Hooks always exit cleanly and never block the agent; storage is hardened for parallel tool calls.
