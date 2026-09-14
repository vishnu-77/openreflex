# Changelog

All notable changes to OpenReflex are listed here. Versions follow [Semantic Versioning](https://semver.org/).

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
