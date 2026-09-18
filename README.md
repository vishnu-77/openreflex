<div align="center">
<!-- mcp-name: io.github.vishnu-77/openreflex -->

<a href="https://openreflex.cc" target="_blank">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/openreflex-banner-dark.svg">
    <img alt="OpenReflex: muscle memory for AI coding agents" src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/openreflex-banner-light.svg" width="720" height="auto">
  </picture>
</a>

<a href="https://openreflex.cc">Website</a> · <a href="https://openreflex.cc/docs">Docs</a> · <a href="docs/walkthrough.md">Walkthrough</a> · <a href="https://pypi.org/project/openreflex/">PyPI</a> · <a href="https://github.com/vishnu-77/openreflex/issues">Issues</a> · <a href="https://buymeacoffee.com/vishnuprashanth">Buy me a coffee</a>

[![PyPI](https://img.shields.io/pypi/v/openreflex?style=flat-square&labelColor=black&color=286a70)](https://pypi.org/project/openreflex/)
[![Python](https://img.shields.io/pypi/pyversions/openreflex?style=flat-square&labelColor=black&color=7cc9c8)](https://pypi.org/project/openreflex/)
[![CI](https://img.shields.io/github/actions/workflow/status/vishnu-77/openreflex/ci.yml?branch=main&style=flat-square&labelColor=black&label=CI)](https://github.com/vishnu-77/openreflex/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-white?style=flat-square&labelColor=black)](https://github.com/vishnu-77/openreflex/blob/main/LICENSE)
[![Glama score](https://glama.ai/mcp/servers/vishnu-77/openreflex/badges/score.svg)](https://glama.ai/mcp/servers/vishnu-77/openreflex)

</div>

***

## What is OpenReflex

OpenReflex gives AI coding agents muscle memory across coding, investigation, and reasoning work. It plugs into
Claude Code, Codex, Cursor, and OpenCode through lifecycle hooks and MCP, quietly records how each task actually
went, and hands the next similar task the useful parts of that experience.

You install it once and keep working normally. Core memory stays on your machine in a local SQLite database.
There is no OpenReflex account or hosted service. Optional Claude token accounting uses Claude Code's local
OpenTelemetry export to a loopback-only OpenReflex receiver and stores counts only.

<p align="center">
  <a href="docs/walkthrough.md">
    <img alt="Recording of a real Claude Code session with OpenReflex: OpenReflex reports one similar past task and adds 162 context tokens, Claude finds and fixes the coupon bug, runs the tests, records the verified outcome through OpenReflex's MCP tool, and OpenReflex shows the completion recap with the path taken and observed cost" src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/docs/screenshots/claude-code-session.gif" width="860">
  </a>
  <br>
  <sub>A real Claude Code session, recorded from the terminal and sped up. OpenReflex had seen one similar task in this repository, so it adds 162 tokens of context before the first tool call; after the fix, Claude records the outcome through OpenReflex's MCP tool. The step-by-step walkthrough is in <a href="docs/walkthrough.md">docs/walkthrough.md</a>.</sub>
</p>

## Why OpenReflex

- **It remembers what worked.** Before a substantial task, OpenReflex retrieves similar past tasks and injects a
  compact Execution Context: a suggested approach with alternatives, the files that were changed, and lessons
  such as which edit resolved a recurring error.
- **It catches loops while they happen.** Repeated failing commands, identical retries, stalled progress, and
  runaway context growth raise one alert that says whether to continue, pivot to another approach, or stop and
  check in with you, never a stream of nags.
- **It learns after every task.** Build work closes against tests/lint/build evidence; investigations can close
  against cross-checked sources; reasoning-only work can complete without external tools. A simple **Path check**
  only names a better option when comparable past tasks actually support one.
- **It is private by design.** Only coarse, project-relative metadata is stored. File contents, commands, tool
  output, and transcripts never are, and capture is off until you approve a project.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/how-it-works-dark.svg">
    <img alt="Before a task: retrieve similar experience, score candidate paths, inject context and a budget. During a task: watch every tool call, flag loops and stalls, advise continue, pivot or stop. After a task: close the outcome using evidence appropriate to the work, run a simple Path check, extract lessons. Lessons feed the Experience Graph for the next task." src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/how-it-works-light.svg" width="860">
  </picture>
</p>

## Quick start

Requires Python 3.11 or newer.

```bash
pipx install openreflex            # or: uv tool install openreflex
cd your-project
openreflex install claude-code     # writes hooks + MCP config and enables this project
```

```
OPENREFLEX / CONNECT
  agent       claude-code
  project     D:\demo\shop
  config      updated 2 files
              D:\demo\shop\.claude\settings.json
              D:\demo\shop\.mcp.json
  memory      enabled
  storage     local

  [ok] reflex active
```

Then work as usual. After a few tasks:

```bash
openreflex context "fix the login redirect bug"   # preview the context a task would receive
openreflex status                                 # what has been captured and learned
openreflex doctor                                 # installation checks and recent hook errors
openreflex update --check                         # check the latest stable release
```

Package updates preserve local memory and project configuration. Managed `pipx` and `uv tool` installs can use
`openreflex update`, `openreflex update --reinstall`, or `openreflex self reinstall`. To remove only the package,
use `openreflex self uninstall --yes`; project memory is preserved. A fresh bootstrap still starts with
`pipx install openreflex` or `uv tool install openreflex` because the `openreflex` command does not exist before installation.

## Use it with your agent

OpenReflex installs per project with `openreflex install <agent>`, or as a plugin.

| Agent | Connects through | Install | Verified |
|---|---|---|---|
| **Claude Code** | Plugin, or hooks + MCP | `claude plugin marketplace add vishnu-77/openreflex` then `claude plugin install openreflex@openreflex`, or `openreflex install claude-code` | Live sessions |
| **Codex** | Plugin, or hooks + MCP | `codex plugin marketplace add vishnu-77/openreflex`, or `openreflex install codex`, then trust the hooks once in `/hooks` | Live sessions |
| **Cursor** | Hooks + MCP | `openreflex install cursor` | Protocol and fuzz tests |
| **OpenCode** | Plugin + MCP | `openreflex install opencode` | Protocol and fuzz tests |

With a plugin install, enable each project with `openreflex approve`. Per-agent guides:
[Claude Code](https://openreflex.cc/claude-code), [Codex](https://openreflex.cc/codex), [Cursor](https://openreflex.cc/cursor),
[OpenCode](https://openreflex.cc/opencode).

## How it works

Hooks send lifecycle events (prompt, tool start, tool end, compaction, stop) to the OpenReflex engine, which
stores them in an **Experience Graph**:

```
Task -caused-> Execution -used-> Context -used-> Experience
CandidatePath -recommended_for-> Task            Lesson -recommended_for-> Task
Execution -failed_with-> ToolCall -resolved_by-> ToolCall
Execution -caused-> Outcome -caused-> Experience -caused-> Lesson
```

- **Before a task:** similar experiences are retrieved and OpenReflex first identifies the work mode. **BUILD**
  uses `inspect-first`, `test-first`, and `incremental`; **INVESTIGATE** uses `source-first`,
  `cross-check`, and `broad-then-deep`; **THINK** uses `reason-first`, `compare-options`, and
  `evidence-first`. Paths are ranked using past evidence, estimated cost, risk, uncertainty and reversibility.
  A compact context is injected only when relevant experience exists.
- **During a task:** when a detector finds a failure loop, repeated calls, stalled progress, context growth,
  or work past the budget, OpenReflex estimates the marginal value of more work. The current path's success
  estimate is updated with each call that makes no progress or fails, and compared with the cost of the work
  left and with the best untried alternative. The alert ends with a recommendation to **continue**, **pivot**
  to another strategy, or **stop** and ask the user. Each problem, pivot, or stop is raised once, with a cooldown
  between messages.
- **After a task:** outcome and chosen path come from the agent's `record_outcome` / `choose_path` MCP calls when
  available, and are otherwise inferred from work-mode-appropriate evidence. The **Path check** says either
  `better option: <path>` when comparable completed tasks support it or `better option: none proven`.
  Recommendations are never presented as paths that were actually executed.

Every recommendation is stored as a decision snapshot with a **Reflex Score** (0-100): how strong the
recommendation is, which is separate from the estimated chance that the task succeeds. `openreflex why` explains
the latest decision and `openreflex trace` shows the timeline. In Claude Code, a short recap appears when a task
starts, when OpenReflex recommends a pivot or stop or detects trouble, and when the task completes.

Set optional limits for every task with `OPENREFLEX_BUDGET`, for example `calls=40,minutes=20,tokens=60000`.
Routing, scoring, budget and recap settings come from a versioned policy: the packaged defaults, overridden by
`~/.openreflex/config.toml` and then by `.openreflex.toml` in the project.

Agents can also query OpenReflex directly through its MCP server.

<details>
<summary><strong>The 12 MCP tools</strong></summary>

| Tool | What it does |
|---|---|
| `get_execution_context` | Plan a task: similar past tasks, the suggested strategy with alternatives, a budget, likely files, lessons. Optional `max_tool_calls`, `max_minutes`, `max_context_tokens`. |
| `check_progress` | Whether more work on the current path is worth it: continue, pivot or stop. |
| `choose_path` | Declare the strategy being followed when it differs from the suggestion. |
| `record_outcome` | Record a confirmed outcome (tests/builds, cross-checked research, user confirmation, or failure) and learn from it. |
| `explain_decision` | Why the latest recommendation was made: Reflex Score, signals, confidence, next-best route. |
| `get_execution_trace` | The decision timeline of the most recent task. |
| `get_reflex_score` | The latest Reflex Score and its components as JSON. |
| `search_experience` | Past tasks in the project by description similarity, with their lessons. |
| `explain_node` | One Experience Graph node and its relations. |
| `get_project_insights` | What has been recorded, reused and learned in the project. |
| `approve_project` | Enable capture, only when the user explicitly asks. |
| `forget_experience` | Delete one past task's memory, only when the user explicitly asks. |

</details>

## CLI

| Command | Purpose |
|---|---|
| `install <agent> [--dry-run]` | Write project hooks and MCP config, and enable the project |
| `uninstall <agent> [--dry-run]` | Remove OpenReflex's project hooks and MCP config; captured memory is kept |
| `update [--check] [--reinstall]` | Check or update a managed pipx/uv-tool installation; optionally force a reinstall |
| `self reinstall` | Repair/reinstall the managed OpenReflex package while preserving memory/config |
| `self uninstall --yes` | Remove only the managed OpenReflex package; memory/config remain on disk |
| `approve` / `revoke` | Enable or disable capture for the current project |
| `context "<task>"` | Preview the Execution Context a task would receive |
| `status [--json]` | What has been captured, reused, learned, and how model-token usage compares |
| `why` / `trace` | Explain the latest recommendation, or show the decision timeline |
| `doctor` | Installation, project resolution, and recent hook activity checks |
| `forget --yes` | Delete the project's data |
| `tokens enable` / `tokens status` / `tokens disable` | Opt in to local Claude Code token accounting, inspect it, or remove OpenReflex-owned telemetry settings |
| `benchmark` | Run the simulated benchmark |
| `hook <agent> <event>` / `mcp` | Used by agent configs |

## Privacy

| Stored | Never stored |
|---|---|
| Tool name and a coarse category (`read`, `edit`, `search`, `test`, ...) | File contents |
| A fingerprint of the arguments | Command text |
| Project-relative file paths | Tool output |
| Pass or fail, duration, output size | Transcripts and model output |
| Optional model-token counts, model/source label, estimated cost | Prompt/response/tool contents from Claude telemetry |
| A masked one-line error signature | Paths outside the project |
| The prompt as a task description (up to 1,000 characters, secrets redacted) | Anything sent to an OpenReflex-hosted service: there is none |

Data lives in `~/.openreflex/projects/<hash>/experience.sqlite3`. Set `OPENREFLEX_HOME` to move it,
`OPENREFLEX_DISABLE=1` to turn capture off everywhere, `openreflex forget --yes` to delete a project's data, or ask
your agent to `forget_experience` a single task.

## Research

OpenReflex is also a research project in budget-aware execution: instead of treating success as a yes or no, it
studies how agents choose execution paths, spend tool calls, model tokens and context, respond to uncertainty, and
whether past work makes similar future work cheaper without reducing outcome quality. The loop is experience
retrieval, evidence-aware path selection, budget-aware execution, work-mode-specific completion and plain-language
path comparison. The [Researcher view](https://openreflex.cc/?view=research) on the site explains the idea,
lets you step through one reflex forming in the graph, and places it next to related work.

## Community & Contributing

- **Issues and ideas:** [GitHub Issues](https://github.com/vishnu-77/openreflex/issues)
- **Support the project:** [Buy me a coffee](https://buymeacoffee.com/vishnuprashanth)
- **Develop locally:**

  ```bash
  git clone https://github.com/vishnu-77/openreflex && cd openreflex
  pip install -e ".[dev]"
  pytest && ruff check src tests scripts
  ```

<a href="https://github.com/vishnu-77/openreflex/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=vishnu-77/openreflex" alt="Contributors">
</a>

OpenReflex is listed in the [MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.vishnu-77/openreflex` and on Glama:

<a href="https://glama.ai/mcp/servers/vishnu-77/openreflex">
  <img src="https://glama.ai/mcp/servers/vishnu-77/openreflex/badges/card.svg" alt="OpenReflex MCP server: quality and maintenance score on Glama" width="380">
</a>

## License

OpenReflex is released under the [MIT License](https://github.com/vishnu-77/openreflex/blob/main/LICENSE).