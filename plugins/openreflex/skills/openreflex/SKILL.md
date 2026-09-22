---
name: openreflex
description: Set up or show OpenReflex for the current project. User-invoked only.
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash
---

Run this command exactly once:

`node "${CLAUDE_PLUGIN_ROOT}/runtime/launcher.cjs" onboard --plugin-root "${CLAUDE_PLUGIN_ROOT}"`

Return the command output directly.

This is the explicit user onboarding/control action for the current project. It may prepare the plugin-managed OpenReflex runtime, enable local project memory, configure the OpenReflex status line when the user has no custom status line, and display the dashboard.

Do not inspect or modify repository files. Do not enable MCP diagnostics. Do not call a global `openreflex` executable from PATH.
