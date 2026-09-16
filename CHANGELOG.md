# Changelog

## Unreleased

- Add `openreflex update` and `openreflex update --check` for managed `pipx` / `uv tool` installs.
- Add `openreflex update --reinstall` and `openreflex self reinstall` to repair/reinstall the managed package without touching local memory or project configuration.
- Add `openreflex self uninstall --yes` to remove the managed package while preserving `~/.openreflex` data and project integration files.
- Self-management fails closed for editable, VCS/source, local-path, ephemeral `uvx`, and unidentified Python environments.

## 0.3.2 - 2026-09-14

Fixes found by an end-to-end test of the published 0.3.1 package.

- A hook event that names no tool (a malformed payload) is ignored. It used to be recorded as a nameless tool call inside a new, untracked task.
- `openreflex why`, `openreflex trace`, `explain_decision`, `get_execution_trace` and `get_reflex_score` explain the most recent task that made a decision. Activity without a captured prompt, such as a resumed session, used to hide the latest explanation behind `No decision snapshot recorded yet.`
- The live Codex test harness reports why Codex refused a run (for example a usage limit) instead of an unrelated stderr line.

## 0.3.1 - 2026-09-14

- Add versioned decision policy and Reflex Score surfaces.
- Add live continue / pivot / stop recommendations and budget controls.
- Add `openreflex why` and `openreflex trace`.
- Expand MCP surface with decision, trace and score tools.

## 0.3.0 - 2026-09-13

- Add project-local experience graph, retrieval and lesson reuse.
- Add Claude Code, Codex, Cursor and OpenCode integrations.
- Add MCP tools for context, path choice, outcomes, search, graph inspection and project insights.
- Add local privacy controls, project approval and forgetting.

Earlier development history is available in Git.