---
name: openreflex
description: Use OpenReflex's local execution memory for this project - check prior experience and suggested strategies before substantial coding tasks, declare a different approach, record verified outcomes, or inspect what has been learned. Use when an [OpenReflex] context or alert appears, or when the user asks what worked before, why a path was suggested, or how tasks have gone.
---

# OpenReflex

OpenReflex captures coding-agent work automatically through lifecycle hooks and learns from it. Everything
stays on this machine. You do not need to do anything for capture to work; the tools below make its advice
more accurate.

## When a task starts

- If the conversation already contains an `[OpenReflex]` block, use it as advice: it lists similar past
  tasks, a suggested strategy with alternatives, likely relevant files, and lessons. Start by checking the
  listed files before broad searching.
- If there is no such block and the task is substantial (a bug fix, feature, refactor, or migration), call
  `get_execution_context` with a one-sentence description of the task.
- If you deliberately take a different approach than the suggested one, call `choose_path` with the strategy
  name (or your own name plus 2-4 short steps). Skip this when you follow the suggestion.

## During the task

An `OpenReflex:` alert means repeated failures, repeated identical calls, stalled progress, or runaway
context growth were detected. Treat it as a prompt to step back: re-read the error, question the current
assumption, or switch to the alternative path it names. Do not retry the same failing action unchanged.

## When the task is done

Once the result is verified (tests or checks pass, or the user confirms), call `record_outcome` with
`status` and short `evidence` (for example "pytest tests/test_auth.py passed"). If the task failed or was
abandoned, record `failure` with the reason. Unverified work is inferred from tool activity, less reliably.

## Questions about history

- "What did we learn / what worked before?" → `search_experience` with the topic.
- "Why was this path suggested?" or a node id → `explain_node`.
- "How is OpenReflex doing?" → `project_insights`.

## Consent

Never call `approve_project` on your own initiative. Call it with `confirm=true` only when the user explicitly
asks to enable OpenReflex for this project.
