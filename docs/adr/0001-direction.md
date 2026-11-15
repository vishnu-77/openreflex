# ADR 0001: OpenReflex is an evidence-governed memory and execution-learning system

- **Status:** Proposed
- **Date:** 2026-11-15
- **Deciders:** project maintainer
- **Supersedes:** the "muscle memory for AI coding agents" framing as the product goal (the phrase may stay as a tagline)

## Principle

**OpenReflex is an evidence-governed memory and execution-learning system, not simply a repository of agent
experiences.** Every memory it keeps, recalls or acts on carries its provenance and the strength of its evidence, and
a stronger claim requires stronger evidence.

## Goal

Combine memory management and execution learning so that, across tasks and sessions, a coding agent:

1. **retains relevant knowledge:** specific, sourced items (files, checks, fixes), not noise or generic filler;
2. **avoids memory drift:** knowledge is not recalled once the code it describes no longer supports it;
3. **recalls verified experience,** saying how strong the evidence is;
4. **reduces rediscovery:** it is pointed to where similar work happened before;
5. **improves efficiency, correctness and decisions,** with correctness as a hard constraint.

The question every change answers: *can an agent use evidence from earlier executions to finish new tasks with less
wasted effort, without losing correctness?*

## Context: what was measured (2026-11-14/15, v0.10.2, local data)

Levels as in the review brief: CONFIRMED, INFERRED, HYPOTHESIS, NOT TESTED.

| Finding | Evidence | Level |
|---|---|---|
| No outcome on the largest project is verified | `togro.co`: 0 verified of 115 person tasks; 84 unknown. A check the hooks see passing is recorded as success but `verified` stays false; only the MCP `record_outcome` call, the agent's own report, sets it (`engine.py`) | CONFIRMED |
| Strongest label on weakest evidence | "verified" means agent-asserted; "proven" Reflexes need it, so they can never form from observed checks | CONFIRMED |
| Machine messages polluted memory | 69 of 182 stored "tasks" were task notifications and subagent hand-backs (before 0.10.0's filter); `status` now leaves them out (PR #48), but Reflex learning still includes them | CONFIRMED |
| Rediscovery is the main opportunity | Chronological replay: about 45% of tasks that touched files revisited files a same-kind earlier task touched; cross-task failure recovery: 0 | CONFIRMED (upper bound on plausible usefulness) |
| Recall beats chance, but barely measurable | Recalled files used on 1 of 4 checkable recalls (25%) against 6% by chance | **Preliminary:** n = 4 |
| Families are too broad, procedures too generic | 94% of tasks match a family with earlier successes; injected procedures read like "check state, check tool, run tests" | CONFIRMED |
| Holdout cannot answer quickly | Tokens per task vary with CV 0.8–2.0; a 20% change needs about 250–1,600 tasks per side | CONFIRMED (power calculation) |
| Live pilot showed no efficiency gain | Click corpus, 18 runs: more tool calls, 2–3 times slower, same tokens; the target file never appeared in the injected context | CONFIRMED (small sample) |
| OpenReflex already blocks | Repeated failing tool calls are denied by default (`hooks.py`, `blocked_retry`) | CONFIRMED |

## Decision

### 1. Evidence semantics

Every outcome records an **evidence level**. The levels are distinct and are never merged into one flag:

| Level | Meaning | Produced by |
|---|---|---|
| `observed` | OpenReflex saw the task end; the status is inferred from what it saw | hooks |
| `agent_reported` | the agent asserted the outcome | MCP `record_outcome` |
| `check_passed` | a test, lint or build check ran after the last edit and passed | hooks |
| `independently_verified` | an external system confirmed the result (for example CI on the pushed commit) | reserved: no source yet |

A passing check verifies **that the check passed**, not that the task was done correctly. So `check_passed` is
reported as such and is never relabelled "correct". In counts that need one bar, "verified" means `check_passed` or
stronger. An agent's report never counts as verified on its own. Outcomes written before levels existed are read
conservatively and are not rewritten.

### 2. Memory lifecycle

Each memory has an explicit lifecycle: **created → consolidated → recalled → invalidated → decayed → deleted.**

- **Created** only from tasks a person asked for (machine messages excluded), with provenance.
- **Consolidated** into Reflexes and file support with dependency links back to their source experiences.
- **Recalled** only when specific (a file pointer, a check, a known fix). Generic procedures are not injected.
- **Invalidated** when the code no longer supports the claim (see 3). That is distinct from deletion.
- **Decayed** when recalls keep going unused, or newer verified evidence contradicts them.
- **Deleted:** deleting an experience removes its influence from every derived Reflex, ranking and index,
  deterministically (recompute from remaining evidence), and deleting it again is a no-op.

### 3. Memory integrity

Memories track **provenance** (source experience, session, agent), **repository revision**, **file hashes** and
**evidence dependencies**. When code changes, claims it no longer supports are **invalidated, not erased**: the
history stays, marked unsupported, and can be revalidated. Recall uses only supported claims.

### 4. Advisory by default; enforcement opt-in

OpenReflex **recommends by default**. Interventions that change what the agent does, starting with today's
blocking of repeated failing calls, become **opt-in**, with a stated reason and an auditable record, until their
false-positive rate is measured. Learning proposes, deterministic policy constrains, the agent or human authorises.
A learned recommendation is never an authorisation grant.

### 5. Evaluation

A change is judged by these, each tracked separately and never folded into one score:

- **Recall precision:** recalls whose files were used, compared with chance.
- **Rediscovery cost:** calls until the first relevant file is reached.
- **Memory contamination:** share of memory derived from non-person or retracted sources.
- **Stale recall:** recalls pointing at changed or deleted code.
- **Correctness:** verified completion, by evidence level.
- Efficiency (time first, tokens second, tool calls as a diagnostic), only where correctness holds.

Efficacy claims need a holdout or a controlled live evaluation with paired comparisons and uncertainty intervals.
Observational numbers are labelled as such. The pane shows "used", never "helped", and no "tokens saved" figure
without such evidence.

## Plan

Each phase ships with tests first, a before/after replay on real data, the pane showing its effect, and no merge or
release without maintainer approval.

| Phase | Scope | Depends on |
|---|---|---|
| **A** | Evidence levels (1); machine messages out of learning; dependency-aware deletion (2) | — |
| **B** | No generic procedure injection; file pointers triggered by the first file a task touches (revised, below) | A |
| **C** | Integrity and drift: revision and hash binding, invalidation, decay on non-use, contradiction handling (2, 3) | A, B |
| **D** | Advisory-by-default enforcement (4); four-condition live evaluation: baseline, map only, memory only, full | A–C |

### Phase B, revised by evidence (2026-11-15)

Before building Phase B as first written (file pointers recalled at prompt time by matching the prompt's wording),
it was replayed on real history, using only the tasks before each task:

| Pointer source | Largest project (`togro.co`) | All projects |
|---|---|---|
| Files from tasks with similar wording (as first planned) | 0 of 11 hit | 2 of 15 |
| Most-touched files so far (no memory; the bar to beat) | 1 of 30 hit | 3 of 34 |
| Files worked on together with the first file the task touches | 2 of 5 hit | **4 of 7** (preliminary: n = 7) |

The wording-based recall picks the wrong past tasks. That is also why 0.10.0 removed "likely files", after 5% of
them were opened. A trigger based on what the agent is actually doing works better. So Phase B became:

- **Prompt time:** inject only specific lessons (known fixes, failure loops). A matched Reflex stays internal; its
  procedure is a generic sequence of tool categories. Explicit plan requests (MCP) still get the full text.
  On `togro.co`, ambient injection drops from 113 tasks to 9.
- **Tool time:** after the first file a task touches, point to the files earlier tasks worked on together with it,
  once per task. Held-out tasks record what they would have been shown, so "used" can be compared with "touched
  anyway".

## Consequences

- Reflexes reach the strongest maturity only from observed checks, not self-reports. Existing projects may show
  fewer verified outcomes at first, because the old count was mostly agent assertions or machine messages.
- Memory gets smaller and more specific. Some recall that happens today will stop, by design.
- Making retry blocking opt-in changes default behaviour. It needs a CHANGELOG entry and a migration note.
- Evaluation needs model credentials and time. Until it is done, OpenReflex claims feasibility, not efficacy.

## Rejected alternatives

- **One "verified" flag, inferred more liberally.** That merges unlike evidence and reproduces today's problem.
- **Estimated "tokens saved" per recall.** It is a counterfactual guess presented as a measurement.
- **Silent command rewriting on similarity.** Risks wrong substitutions and injection, and commands are not stored
  anyway (privacy by design).
- **Optimising a single efficiency score.** It hides correctness regressions.
