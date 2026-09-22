# OpenReflex evaluation

OpenReflex separates three kinds of evidence:

1. **Regression tests** prove implementation behaviour and run on every pull request.
2. **Deterministic simulation/localisation benchmarks** test routing and retrieval contracts under declared assumptions.
3. **Real-agent paired evaluations** compare the same pinned repository task with and without OpenReflex using real Claude Code.

Real-agent results are stored as workflow artifacts. A negative treatment result is valid evidence and does not fail the
workflow merely for being negative. The live workflow fails when the experiment itself is invalid, such as a repository
commit mismatch or OpenReflex treatment context not reaching the model.

## Current live corpus: Click cold start v1

The machine-readable source of truth is `evals/cold_start/click.json`.

- Repository: `pallets/click`
- Commit: `3cbaa76b6014be7427d1ab06b4af40f01e7c278e`
- Claude Code: `2.1.278`
- Model: `claude-sonnet-4-6`
- Tools: `Read`, `Grep`, `Glob`
- Default repetitions: 3 paired repetitions per task
- Conditions:
  - **baseline** — plain Claude Code, no OpenReflex plugin or hooks.
  - **primed** — OpenReflex enabled with a freshly built Project Map and no prior Experience.

Each pair starts from an independent local clone of the same repository commit, preserving the pinned repository's Git history for both arms. Baseline/treatment order is deterministically shuffled inside each task/repetition pair.

### Prompts

**Shell completion dispatch**

> Without editing any files, investigate where Click parses the shell-completion instruction (such as source versus
> complete), selects the shell completion implementation, and writes the completion output. Reply with the single file
> path relative to the repository root that contains that implementation, and a one-sentence summary.

Reviewed target: `src/click/shell_completion.py`

**Choice conversion**

> Without editing any files, investigate where Click normalizes a Choice option's raw value, compares it with the
> configured choices, and returns the matching original choice. Reply with the single file path relative to the
> repository root that contains that implementation, and a one-sentence summary.

Reviewed target: `src/click/types.py`

**Help width**

> Without editing any files, investigate where Click's help formatter determines its default text width from the
> terminal size and clamps it to a maximum width. Reply with the single file path relative to the repository root that
> contains that implementation, and a one-sentence summary.

Reviewed target: `src/click/formatting.py`

## Metrics

The live harness records per run:

- correctness: whether the target was actually inspected and named in the answer;
- observed Claude input/output/cache tokens;
- exploration and total tool calls;
- wall-clock time;
- reported API cost;
- whether OpenReflex context reached Claude;
- target rank in the injected project context.

The paired summary reports treatment-vs-baseline relative changes. These Click results are a **pilot** and must not be
generalised into a broad token-savings claim. A broader efficacy claim requires a multi-repository, multi-task benchmark
with sufficient repetitions and a predeclared quality/non-inferiority criterion.

## CI/CD

`.github/workflows/live-agent-eval.yml` runs weekly and can also be invoked manually. It requires either the repository
secret `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. The workflow installs the pinned Claude Code version, checks out the exact corpus commit, runs the
paired evaluation, publishes a GitHub Actions job summary, and retains the raw JSON results as an artifact for 30 days.

The normal `CI` workflow does not spend model tokens. It validates the evaluation manifest and summarisation logic
through `tests/test_live_eval.py`.
