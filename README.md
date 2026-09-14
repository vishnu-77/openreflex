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

OpenReflex gives AI coding agents muscle memory. It plugs into Claude Code, Codex, Cursor, and OpenCode through
lifecycle hooks and MCP, quietly records how each task actually went, and hands the next similar task what worked
before: the approach, the files that mattered, and the fix for the error you hit last time.

You install it once and keep working normally. Everything stays on your machine in a local SQLite database.
There is no account, no service, and no telemetry.

<p align="center">
  <a href="docs/walkthrough.md">
    <img alt="A real Claude Code session with OpenReflex: the UserPromptSubmit line shows one past experience found and 162 context tokens added; the Stop line shows a verified success, the path taken and the cost" src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/docs/screenshots/claude-code-session-2.png" width="860">
  </a>
  <br>
  <sub>A real Claude Code session in a repository where OpenReflex had seen one similar task. The full walkthrough, with both sessions and the exact context the model received, is in <a href="docs/walkthrough.md">docs/walkthrough.md</a>.</sub>
</p>

## Why OpenReflex

- **It remembers what worked.** Before a substantial task, OpenReflex retrieves similar past tasks and injects a
  compact Execution Context: a suggested approach with alternatives, the files that were changed, and lessons
  such as which edit resolved a recurring error.
- **It catches loops while they happen.** Repeated failing commands, identical retries, stalled progress, and
  runaway context growth raise one alert that says whether to continue, pivot to another approach, or stop and
  check in with you, never a stream of nags.
- **It learns after every task.** OpenReflex infers the outcome from real verification (a test or build that
  passed or failed after the last edit), estimates Execution Regret against the alternatives, and extracts lessons.
- **It is private by design.** Only coarse, project-relative metadata is stored. File contents, commands, tool
  output, and transcripts never are, and capture is off until you approve a project.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/how-it-works-dark.svg">
    <img alt="Before a task: retrieve similar experience, score candidate paths, inject context and a budget. During a task: watch every tool call, flag loops and stalls, advise continue, pivot or stop. After a task: infer the outcome from checks, estimate Execution Regret, extract lessons. Lessons feed the Experience Graph for the next task." src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/how-it-works-light.svg" width="860">
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
```

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

- **Before a task:** similar experiences are retrieved and three strategies (`inspect-first`, `test-first`,
  `incremental`) are estimated on success probability, time, tool calls, context cost, risk, uncertainty,
  reversibility, and expected regret. Strategies that another one beats on every measure are dropped as
  dominated (Pareto efficiency), the rest are ranked by utility within any limits you set, and the chosen path
  gets an execution budget for time, tool calls, and context. A context of at most 1,400 characters is
  injected; nothing is injected without relevant experience.
- **During a task:** when a detector finds a failure loop, repeated calls, stalled progress, context growth,
  or work past the budget, OpenReflex estimates the marginal value of more work. The current path's success
  estimate is updated with each call that makes no progress or fails, and compared with the cost of the work
  left and with the best untried alternative. The alert ends with a recommendation to **continue**, **pivot**
  to another strategy, or **stop** and ask the user. Each problem, pivot, or stop is raised once, with a cooldown
  between messages.
- **After a task:** outcome and chosen path come from the agent's `record_outcome` / `choose_path` MCP calls when
  available, and are otherwise inferred from tool activity. Execution Regret compares the path taken with the
  best plausible alternative; it is withheld when the outcome is unknown, and feeds back into how strategies
  are ranked next time, along with success, cost, and how often a strategy ran into trouble.

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
| `record_outcome` | Record a verified outcome (tests passed, user confirmed, or failure) and learn from it. |
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
| `approve` / `revoke` | Enable or disable capture for the current project |
| `context "<task>"` | Preview the Execution Context a task would receive |
| `status [--json]` | What has been captured, reused, and learned |
| `why` / `trace` | Explain the latest recommendation, or show the decision timeline |
| `doctor` | Installation, project resolution, and recent hook activity checks |
| `forget --yes` | Delete the project's data |
| `benchmark` | Run the simulated benchmark |
| `hook <agent> <event>` / `mcp` | Used by agent configs |

## Privacy

| Stored | Never stored |
|---|---|
| Tool name and a coarse category (`read`, `edit`, `search`, `test`, ...) | File contents |
| A fingerprint of the arguments | Command text |
| Project-relative file paths | Tool output |
| Pass or fail, duration, output size | Transcripts and model output |
| A masked one-line error signature | Paths outside the project |
| The prompt as a task description (up to 1,000 characters, secrets redacted) | Anything sent to a server: there is none |

Data lives in `~/.openreflex/projects/<hash>/experience.sqlite3`. Set `OPENREFLEX_HOME` to move it,
`OPENREFLEX_DISABLE=1` to turn capture off everywhere, `openreflex forget --yes` to delete a project's data, or ask
your agent to `forget_experience` a single task.

## Research

OpenReflex is also a research project in budget-aware execution: instead of treating success as a yes or no, it
studies how agents choose execution paths, spend tool calls and context, respond to uncertainty, and whether more
computation still adds value. The loop is experience retrieval, Pareto path selection, budget-aware execution and
counterfactual regret. The [Researcher view](https://openreflex.cc/?view=research) on the site explains the idea,
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
