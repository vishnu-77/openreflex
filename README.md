<div align="center">

<a href="https://openreflex.vercel.app" target="_blank">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/openreflex-logo-dark.svg">
    <img alt="OpenReflex" src="https://raw.githubusercontent.com/vishnu-77/openreflex/main/assets/openreflex-logo-light.svg" width="380" height="auto">
  </picture>
</a>

### OpenReflex: muscle memory for AI coding agents

<a href="https://openreflex.vercel.app">Website</a> · <a href="https://github.com/vishnu-77/openreflex">GitHub</a> · <a href="https://pypi.org/project/openreflex/">PyPI</a> · <a href="https://github.com/vishnu-77/openreflex/issues">Issues</a> · <a href="https://buymeacoffee.com/vishnuprashanth">Buy me a coffee</a>

[![PyPI](https://img.shields.io/pypi/v/openreflex?style=flat-square&labelColor=black&color=286a70)](https://pypi.org/project/openreflex/)
[![Python](https://img.shields.io/pypi/pyversions/openreflex?style=flat-square&labelColor=black&color=7cc9c8)](https://pypi.org/project/openreflex/)
[![CI](https://img.shields.io/github/actions/workflow/status/vishnu-77/openreflex/ci.yml?branch=main&style=flat-square&labelColor=black&label=CI)](https://github.com/vishnu-77/openreflex/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-white?style=flat-square&labelColor=black)](https://github.com/vishnu-77/openreflex/blob/main/LICENSE)

</div>

***

## What is OpenReflex

OpenReflex gives AI coding agents muscle memory. It plugs into Claude Code, Codex, Cursor, and OpenCode through
lifecycle hooks and MCP, quietly records how each task actually went, and hands the next similar task what worked
before: the approach, the files that mattered, and the fix for the error you hit last time.

You install it once and keep working normally. Everything stays on your machine in a local SQLite database.
There is no account, no service, and no telemetry.

## Why OpenReflex

- **It remembers what worked.** Before a substantial task, OpenReflex retrieves similar past tasks and injects a
  compact Execution Context: a suggested approach with alternatives, the files that were changed, and lessons
  such as which edit resolved a recurring error.
- **It catches loops while they happen.** Repeated failing commands, identical retries, stalled progress, and
  runaway context growth raise a single, specific alert with an alternative path, never a stream of nags.
- **It learns after every task.** OpenReflex infers the outcome from real verification (a test or build that
  passed or failed after the last edit), estimates Execution Regret against the alternatives, and extracts lessons.
- **It is private by design.** Only coarse, project-relative metadata is stored. File contents, commands, tool
  output, and transcripts never are, and capture is off until you approve a project.

```
        before a task                  during a task                 after a task
  ┌──────────────────────┐    ┌──────────────────────────┐    ┌───────────────────────┐
  │ retrieve experience  │    │ watch tool calls         │    │ infer outcome         │
  │ score candidate paths│ →  │ flag loops and stalls    │ →  │ estimate regret       │
  │ inject context       │    │ suggest an alternative   │    │ extract lessons       │
  └──────────────────────┘    └──────────────────────────┘    └───────────────────────┘
                 ▲                                                        │
                 └──────────────────── Experience Graph ◄─────────────────┘
```

## Quick start

Requires Python 3.11 or newer.

```bash
pipx install openreflex            # or: uv tool install openreflex
cd your-project
openreflex install claude-code     # writes hooks + MCP config and enables this project
```

Then work as usual. After a few tasks:

```bash
openreflex context "fix the login redirect bug"   # preview the context a task would receive
openreflex status                                 # what has been captured and learned
openreflex doctor                                 # installation checks and recent hook errors
```

## Use it with your agent

OpenReflex installs per project with `openreflex install <agent>`, or as a plugin.

<table>
  <tbody>
    <tr>
      <td align="center" valign="bottom" width="25%"><strong>Claude&nbsp;Code</strong><br><sub>Plugin&nbsp;or&nbsp;hooks&nbsp;+&nbsp;MCP</sub></td>
      <td align="center" valign="bottom" width="25%"><strong>Codex</strong><br><sub>Plugin&nbsp;or&nbsp;hooks&nbsp;+&nbsp;MCP</sub></td>
      <td align="center" valign="bottom" width="25%"><strong>Cursor</strong><br><sub>Hooks&nbsp;+&nbsp;MCP</sub></td>
      <td align="center" valign="bottom" width="25%"><strong>OpenCode</strong><br><sub>Plugin&nbsp;+&nbsp;MCP</sub></td>
    </tr>
  </tbody>
</table>

| Agent | Install |
|---|---|
| Claude Code | `claude plugin marketplace add vishnu-77/openreflex` and `claude plugin install openreflex@openreflex`, or `openreflex install claude-code` |
| Codex | `codex plugin marketplace add vishnu-77/openreflex`, or `openreflex install codex`, then trust the hooks once in `/hooks` |
| Cursor | `openreflex install cursor` |
| OpenCode | `openreflex install opencode` |

With a plugin install, enable each project with `openreflex approve`. Claude Code is verified in live sessions;
the Codex, Cursor, and OpenCode integrations follow each agent's documented hook protocol.

## How it works

Hooks send lifecycle events (prompt, tool start, tool end, compaction, stop) to the OpenReflex engine, which
stores them in an **Experience Graph**:

```
Task -caused-> Execution -used-> Context -used-> Experience
CandidatePath -recommended_for-> Task            Lesson -recommended_for-> Task
Execution -failed_with-> ToolCall -resolved_by-> ToolCall
Execution -caused-> Outcome -caused-> Experience -caused-> Lesson
```

- **Before a task:** similar experiences are retrieved, three strategies (`inspect-first`, `test-first`,
  `incremental`) are scored on success probability, time, tool calls, context cost, risk, uncertainty, and
  reversibility, and a context of at most 1,400 characters is injected. Nothing is injected without relevant
  experience.
- **During a task:** each alert fires at most once per task with a cooldown, and names a concrete alternative.
- **After a task:** outcome and chosen path come from the agent's `record_outcome` / `choose_path` MCP calls when
  available, and are otherwise inferred from tool activity. Execution Regret is withheld when the outcome is unknown.

Agents can also query OpenReflex directly through its MCP server: `get_execution_context`, `choose_path`,
`record_outcome`, `search_experience`, `explain_node`, `project_insights`, and `approve_project`.

## CLI

| Command | Purpose |
|---|---|
| `install <agent> [--dry-run]` | Write project hooks and MCP config, and enable the project |
| `approve` / `revoke` | Enable or disable capture for the current project |
| `context "<task>"` | Preview the Execution Context a task would receive |
| `status [--json]` | What has been captured, reused, and learned |
| `doctor` | Installation checks and recent hook errors |
| `forget --yes` | Delete the project's data |
| `benchmark` | Run the simulated benchmark |
| `hook <agent> <event>` / `mcp` | Used by agent configs |

## Privacy

- Stored per tool call: tool name, a coarse category (`read`, `edit`, `search`, `test`, ...), a fingerprint of the
  arguments, project-relative file paths, status, duration, output size, and a masked one-line error signature.
- Never stored: file contents, command text, tool output, transcripts, or paths outside the project.
- Prompts are kept as task descriptions (up to 1,000 characters) with secrets such as API keys and tokens redacted.
- Data lives in `~/.openreflex/projects/<hash>/experience.sqlite3`. Set `OPENREFLEX_HOME` to move it,
  `OPENREFLEX_DISABLE=1` to turn capture off everywhere, or run `openreflex forget --yes` to delete a project's data.

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

## License

OpenReflex is released under the [MIT License](https://github.com/vishnu-77/openreflex/blob/main/LICENSE).
