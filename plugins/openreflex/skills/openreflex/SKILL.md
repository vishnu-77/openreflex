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
  tasks, a suggested strategy with alternatives (strategies that are worse on every measure are marked
  dominated), an execution budget, likely relevant files, and lessons. Start by checking the listed files
  before broad searching, and aim to finish within the budget.
- If there is no such block and the task is substantial (a bug fix, feature, refactor, or migration), call
  `get_execution_context` with a one-sentence description of the task. If the user gave limits ("keep it
  quick", "no more than 20 minutes"), pass them as `max_minutes`, `max_tool_calls` or `max_context_tokens`.
- If you deliberately take a different approach than the suggested one, call `choose_path` with the strategy
  name (or your own name plus 2-4 short steps). Skip this when you follow the suggestion.

## During the task

An `OpenReflex:` alert means repeated failures, repeated identical calls, stalled progress, runaway context
growth, or work past the budget were detected. Each alert ends with a recommendation:

- **continue**: the path is still worth it; fix the approach within it (re-read the error, question the
  current assumption). Do not retry the same failing action unchanged.
- **pivot**: switch to the named strategy and follow its steps.
- **stop**: more work is unlikely to pay off. Stop, summarize what was tried and what failed, and ask the user
  how to proceed.

When you are unsure whether more work is paying off, call `check_progress` for the same estimate on demand.

## When the task is done

Once the result is verified (tests or checks pass, or the user confirms), call `record_outcome` with
`status` and short `evidence` (for example "pytest tests/test_auth.py passed"). If the task failed or was
abandoned, record `failure` with the reason. Unverified work is inferred from tool activity, less reliably.

## Questions about history

- "What did we learn / what worked before?" → `search_experience` with the topic.
- "Why was this path suggested?" or a node id → `explain_node`.
- "How is OpenReflex doing?" → `get_project_insights`.
- "Forget what you learned from that task" → `forget_experience` with the experience id, only when the user explicitly asks.

## Consent

Never call `approve_project` or `forget_experience` on your own initiative. Call them with `confirm=true` only
when the user explicitly asks to enable OpenReflex for this project, or to forget a specific past task.
