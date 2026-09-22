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

OpenReflex gives AI coding agents ambient project muscle memory across coding, investigation, and reasoning work.
Lifecycle hooks quietly record how work actually goes, compile repeated project behaviour into reusable Reflexes,
and inject only the relevant project procedure into new tasks. The model does not need to remember to call OpenReflex,
and MCP diagnostics are opt-in rather than loaded into normal agent context.

You install it once and keep working normally. Core memory stays on your machine in a local SQLite database.
There is no OpenReflex account or hosted service. Optional Claude token accounting uses Claude Code's local
OpenTelemetry export to a loopback-only OpenReflex receiver and stores counts only.

<p align="center">
  <a href="docs/walkthrough.md">
    <img alt="Recording of a Claude Code session with OpenReflex: OpenReflex injects compact prior context, Claude fixes the task and runs verification, and lifecycle hooks close the outcome automatically" src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/docs/screenshots/claude-code-session.gif" width="860">
  </a>
  <br>
  <sub>A recorded Claude Code session. OpenReflex injects compact relevant context before work; lifecycle hooks capture tools and verification and close the execution automatically. MCP is not required for the normal path. The step-by-step walkthrough is in <a href="docs/walkthrough.md">docs/walkthrough.md</a>.</sub>
</p>

## Why OpenReflex

- **It learns how the project behaves.** OpenReflex compiles successful work into project-scoped Reflexes such as
  authentication changes, Helm configuration, database migrations or CI work. Resolution combines semantic intent,
  task family and module/file locality, so a novel task can reuse a project procedure without repeating an
  earlier task.
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

**Claude Code — recommended:** install the plugin, reload it, inspect the current state, then explicitly enable
project memory.

```text
/plugin marketplace add vishnu-77/openreflex
/plugin install openreflex@openreflex
/reload-plugins
/openreflex
/openreflex approve
```

Claude may display the canonical plugin namespace as `/openreflex:openreflex`; both refer to the same user-invoked
OpenReflex control surface when the bare alias is available. The no-argument command is read-only and compact.
`approve` explicitly enables local memory for the current project. The plugin prepares an exact-version runtime
under `~/.openreflex/runtime/` and normal agent work remains ambient after approval.

The Claude plugin does **not** execute a global `openreflex` from PATH. An older pipx/uv/pip installation can coexist
without taking over the plugin runtime.

**CLI / other agents:** use a persistent package install.

```bash
pipx install openreflex            # or: uv tool install openreflex
cd your-project
openreflex install codex           # or cursor / opencode / claude-code
```

After a few tasks:

```bash
openreflex context "fix the login redirect bug"   # preview the context a task would receive
openreflex status                                 # what has been captured and learned
openreflex doctor                                 # installation checks and recent hook errors
openreflex update --check                         # check the latest stable release
```

Package updates preserve local memory and project configuration. Managed `pipx` and `uv tool` installs can use
`openreflex update`, `openreflex update --reinstall`, or `openreflex self reinstall`. The Claude plugin manages
its own pinned runtime automatically; these package-manager commands are only needed for standalone CLI installs.

## Use it with your agent

OpenReflex installs per project with `openreflex install <agent>`, or as a plugin.

| Agent | Connects through | Install | Verified |
|---|---|---|---|
| **Claude Code** | Plugin hooks, or project hooks | `claude plugin marketplace add vishnu-77/openreflex` then `claude plugin install openreflex@openreflex`, or `openreflex install claude-code` | Live sessions |
| **Codex** | Plugin hooks, or project hooks | `codex plugin marketplace add vishnu-77/openreflex`, or `openreflex install codex`, then trust the hooks once in `/hooks` | Live sessions |
| **Cursor** | Lifecycle hooks | `openreflex install cursor` | Protocol and fuzz tests |
| **OpenCode** | Local lifecycle plugin | `openreflex install opencode` | Protocol and fuzz tests |

With the Claude plugin, `/openreflex` shows a compact read-only state view. Use `/openreflex approve` to enable
local memory for the current project, then work normally. Other explicit controls include `status`, `reflexes`,
`memory`, `doctor`, `why`, `trace`, and `revoke`. OpenReflex control turns are not learned as project
experiences and do not trigger normal task verification. The control skill is user-invoked only and does not enable
MCP diagnostics or participate in normal model routing. Claude may show the canonical namespaced form
`/openreflex:openreflex`. Per-agent guides:
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
- **After a task:** lifecycle hooks close the execution automatically from work-mode-appropriate evidence; the model
  does not need to call OpenReflex. Explicit MCP outcome/path operations remain available only for manual or diagnostic
  workflows. The **Path check** says either
  `better option: <path>` when comparable completed tasks support it or `better option: none proven`.
  Recommendations are never presented as paths that were actually executed.

Every recommendation is stored as a decision snapshot with a **Reflex Score** (0-100): how strong the
recommendation is, which is separate from the estimated chance that the task succeeds. `openreflex why` explains
the latest decision and `openreflex trace` shows the timeline. In Claude Code, a short recap appears when a task
starts, when OpenReflex recommends a pivot or stop or detects trouble, and when the task completes.

Set optional limits for every task with `OPENREFLEX_BUDGET`, for example `calls=40,minutes=20,tokens=60000`.
Routing, scoring, budget and recap settings come from a versioned policy: the packaged defaults, overridden by
`~/.openreflex/config.toml` and then by `.openreflex.toml` in the project.

Normal work does **not** load OpenReflex MCP tools. If you explicitly want model-facing introspection for a project,
enable it with `openreflex diagnostics enable <agent>`. Disable it again with
`openreflex diagnostics disable <agent>`. The standalone MCP Registry package remains available for users who
deliberately install OpenReflex as an MCP server.

<details>
<summary><strong>The optional MCP diagnostics/admin tools</strong></summary>

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
| `install <agent> [--dry-run]` | Install the hooks-only ambient runtime and enable the project |
| `diagnostics enable/disable <agent>` | Explicitly opt in/out of model-facing MCP diagnostics |
| `uninstall <agent> [--dry-run]` | Remove OpenReflex's integration entries; captured memory is kept |
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
| `hook <agent> <event>` | Used by ambient agent integrations |
| `mcp` | Run the optional diagnostics/admin MCP server explicitly |

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