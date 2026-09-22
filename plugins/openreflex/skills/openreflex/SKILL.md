---
name: openreflex
description: OpenReflex project control. Show state, enable memory, inspect Reflexes, or run diagnostics.
argument-hint: "[approve|status|reflexes|memory|doctor|why|trace|revoke]"
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash
---

OPENREFLEX_CONTROL_REQUEST: $ARGUMENTS

Run exactly one command:

`node "${CLAUDE_PLUGIN_ROOT}/runtime/launcher.cjs" control --plugin-root "${CLAUDE_PLUGIN_ROOT}" --request "$ARGUMENTS"`

Return the command output directly, with no preamble, summary, interpretation, or follow-up.

The argument is an explicit user request. If the user invokes `approve` or `revoke`, execute that requested OpenReflex state change without asking for another confirmation. Destructive memory deletion is not exposed by this skill.

Do not inspect or modify repository files. Do not enable MCP diagnostics. Do not call a global `openreflex` executable from PATH. Do not mention internal launcher, TUI, Python, shell, or runtime implementation details unless the command itself reports a failure.
