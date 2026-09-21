# Changelog

All notable changes to OpenReflex are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

## 0.8.0 (2026-09-21)

- Let one execution reinforce multiple project scopes instead of forcing it into a single family. A runner change can
  now contribute separately to Terraform, Helm chart/template and a shared project-area Reflex.
- Add stable project-area scopes derived from meaningful compound paths, so
  `helm/bitbucket-runner/...` and `docs/bitbucket-runner-plan.md` reinforce the same
  `Bitbucket runner work` memory without merging their underlying procedures.
- Make project-area Reflexes work-mode agnostic: BUILD implementation, THINK/planning, INVESTIGATE and documentation
  work can reinforce the same project area while technology/procedure Reflexes remain mode-specific.
- Carry project-area scope hints across explicit contextual follow-ups in the same agent session, allowing prompts
  such as "Where is the implementation plan committed?" to reuse the project area learned by the immediately
  preceding task without requiring the user to repeat the component name.
- Fix the TUI/state parser for the current `Reflex: <name> · learned/proven.` context format and display Reflex
  maturity in CURRENT REFLEX.
- Add regression coverage using the real GCP Bitbucket runner → implementation plan → follow-up lifecycle, including
  an assertion that no backend strategy name such as `test-first` or `inspect-first` leaks into learned Reflex context.


## 0.7.0 (2026-09-21)

- Make OpenReflex ambient by default: normal operation is lifecycle hooks only, with no model-invocable OpenReflex
  skill and no automatically loaded MCP server.
- Remove the packaged `SKILL.md` and plugin `.mcp.json`; Codex and Cursor plugin manifests no longer advertise
  skills or MCP servers. The agent never has to remember to invoke OpenReflex for capture, retrieval or learning.
- Change project installers for Claude Code, Codex, Cursor and OpenCode to install hooks only. Re-running the default
  installer also removes legacy OpenReflex MCP entries from pre-0.7 project configuration.
- Add `openreflex diagnostics enable|disable <agent>` for explicit, project-scoped MCP introspection/admin access.
  The standalone MCP server and Registry listing remain available for deliberate MCP users.
- Keep learned Project Reflex injection under 900 characters (about 225 tokens at the default estimator) and remove
  routine Stop-hook instructions to call `record_outcome`.
- Add first-class overhead accounting: estimated injected context tokens, zero-injection substantial tasks,
  optional diagnostic MCP calls/result tokens, observed model tokens and estimated context tax.
- Count diagnostic MCP response overhead locally without storing prompts, tool arguments or response content.
- Align Python, runtime, Claude/Codex/Cursor plugin and MCP Registry metadata on version 0.7.0.


## 0.6.0 (2026-09-21)

- Make Project Reflexes reusable across heterogeneous work rather than requiring the same task to recur. Domain
  families such as authentication, database, CI, deployment, API, cache and configuration accumulate evidence
  across bug fixes, features and refactors within the same project.
- Replace task-class-gated Reflex matching with a multi-signal project resolver combining semantic intent,
  project-family compatibility, file/module locality, task-class compatibility and accumulated execution evidence.
- Learn common module scopes (for example `src/auth`) in addition to exact common files, allowing a new task in
  the same subsystem to reuse project procedure even when it touches a file OpenReflex has never seen before.
- Keep unrelated mature Reflexes out of context with a minimum relationship gate; project evidence alone is never
  enough to inject a Reflex.
- Count tasks that reused a Project Reflex as memory reuse even when no individual historical episode was injected.
- Align the Python package, runtime, Claude/Codex/Cursor plugin manifests and MCP Registry package metadata on
  version 0.6.0.


## 0.5.3 (2026-09-21)

- Improve cold-start retrieval ranking: broaden the query stopword list beyond bug-fixing jargon, and stem
  `-ing` suffixes so phrasing like "wrapping" matches a symbol named `wrap_text`. Verified against a real
  repository: 2 of 3 pilot tasks now rank the correct file first, up from 1 of 3.
- Add path visibility: `get_candidate_paths` (MCP) and the TUI dashboard now show every strategy OpenReflex
  considered for a task, which one was recommended, and which one was actually followed - explicit
  (`choose_path`) or inferred from tool-call evidence.
- Trim repeated static boilerplate from the context injected into every prompt (a fixed "Evidence: ..."
  sentence, an over-long advisory line, and oversized symbol listings).

## 0.5.2 (2026-09-20)

- Fix a `UnicodeEncodeError` that crashed `openreflex tui`, `openreflex statusline`, and bare `openreflex` on a
  Windows console using a legacy (non-UTF-8) codepage. `entrypoint.main()` dispatches several commands before
  ever reaching the CLI's UTF-8 stdio setup; it now configures stdout/stderr encoding itself, first.

## 0.5.1 (2026-09-18)

Fixes found by a local QA pass of the released 0.5.0 package.

- A WAITING execution now resumes on the next prompt for that session even when the text is not byte-identical to
  the original, instead of being silently finalized as unknown.
- A trivial zero-tool response (for example a single character) is no longer recorded as a completed, reusable
  THINK-mode experience.
- `openreflex tokens disable` now actually stops the local receiver instead of only rewriting Claude Code's
  telemetry settings.
- The receiver health check now verifies it is actually the OpenReflex token receiver on 127.0.0.1:4319, rather than
  treating any process on that port as one.
- The Windows UI-state lock's stale-lock reclaim can now actually trigger before a default caller times out.
- `openreflex tokens --help` and an unknown `tokens` action now print usage instead of an unhandled error, and the
  `tui`/`memory`/`tokens`/`statusline` commands are mentioned in `openreflex --help`.

## 0.5.0 (2026-09-18)

General agent work memory beyond edit/test coding loops, with truthful token accounting.

- Add three work modes: **BUILD**, **INVESTIGATE**, and **THINK**. Coding keeps inspect/test/incremental paths;
  investigation gets source-first/cross-check/broad-then-deep; reasoning gets reason-first/compare-options/evidence-first.
- Read Claude Code Stop metadata so active background work and /loop schedules remain **WAITING** instead of being
  incorrectly finalized as complete.
- Treat substantive zero-tool reasoning and investigation as real executions. Recommendations stay separate from
  observed paths, so OpenReflex never claims a suggested path was executed when it was not observed.
- Replace user-facing numeric path-comparison jargon with a plain **Path check**: either a better option supported by
  comparable completed tasks, or **none proven**.
- Add opt-in Claude Code model-token accounting through a loopback-only OTLP/HTTP receiver. Store input, output,
  cache-read, cache-creation counts, model/source labels and estimated cost; prompt, response, thinking, tool
  arguments and raw API bodies remain disabled.
- Show real model-token totals in the status line, TUI and observational efficiency metrics when available. Legacy
  tool-output estimates are labelled separately and zero tool calls are never presented as zero model usage.
- Harden Windows UI-state locking by treating transient access-denied errors as bounded lock contention.

## 0.4.1 (2026-09-17)

Truthful Claude Code runtime presentation and completion semantics.

- Unknown outcomes now render as `UNVERIFIED`, failures as `FAILED`, and only known successful outcomes render as
  `COMPLETE`. Unknown outcomes never display Execution Regret, including legacy snapshots that stored `0.00`.
- A task that stops unverified and then continues to verification now receives a fresh final completion snapshot;
  the first unknown Stop can no longer mask the later verified result.
- The Claude status line tracks `PreToolUse` and shows the current safe operation (`READ`, `SEARCH`, `EDIT`, `TEST`,
  `LINT`, `BUILD`, `GIT`, `WEB`, `MCP`, `RUN`, etc.) plus completed-call count. Raw shell commands are never echoed.
- A new task resets stale activity/call state, and a live task transitions from `RECALL` to `WATCH` rather than
  incorrectly appearing `READY` while work is still in progress.
- Runtime/version diagnostics distinguish the installed OpenReflex package, Claude plugin manifest and MCP runtime.
  Matching versions show `ALIGNED`; mixed plugin/runtime versions show `VERSION MISMATCH`.
- Claude plugin hooks carry `${CLAUDE_PLUGIN_ROOT}` so reloads can report the plugin version actually loaded by
  Claude without persisting the plugin cache path.

## 0.4.0 (2026-09-17)

Managed project memory and cold-start intelligence, while keeping normal agent startup non-blocking.

- Add a non-blocking Project Primer and managed project-memory snapshot with provenance, freshness and stale-fact
  handling. Claude can start working immediately while project understanding is built/refreshed locally.
- Add ReflexIndex reinforcement so structural project priors can be strengthened by observed and verified execution
  evidence without treating repository inference as proof that a route worked.
- Add Project Map indexing for tracked files, lightweight symbols, dependency names, Git hotspots, co-change
  relationships and nested Helm/Node/Python manifests. Source bodies are not persisted.
- Add compact hybrid retrieval that combines project structure with execution/lesson evidence and keeps verified
  outcomes stronger than structural/Git priors.
- Add the OpenReflex Claude status line and standalone TUI with the lifecycle
  `REFLEXING -> READY -> RECALL -> WATCH -> VERIFY -> REMEMBER`.
- Add one-shot outcome closure plus Helm/Kubernetes verification recognition so changed tasks can be closed against
  test/lint/build evidence instead of silently remaining unknown.
- Add a model-free cold-start localisation benchmark covering nested manifests and target-file retrieval.
- Add `openreflex update` / `openreflex update --check`, managed reinstall/self-uninstall commands, and fail-closed
  handling for editable, VCS/source, local-path, ephemeral `uvx`, and unidentified Python environments.

## 0.3.2 (2026-09-15)

Fixes found by an end-to-end test of the published 0.3.1 package.

- A hook event that names no tool (a malformed payload) is ignored. It used to be recorded as a nameless tool call
  inside a new, untracked task.
- `openreflex why`, `openreflex trace`, `explain_decision`, `get_execution_trace` and `get_reflex_score` explain the
  most recent task that made a decision. Activity without a captured prompt, such as a resumed session, used to hide
  the latest explanation behind "No decision snapshot recorded yet."
- The live Codex test harness reports why Codex refused a run (for example a usage limit) instead of an unrelated
  stderr line.

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
