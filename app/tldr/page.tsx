import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { Navbar } from "@/components/Navbar";
import { LINKS } from "@/lib/site";

export const metadata: Metadata = {
  title: "TLDR | OpenReflex",
  description:
    "OpenReflex in one page: managed project memory, ReflexIndex, Project Map, verification lifecycle, privacy, work modes, real token accounting and the 0.5.0 live runtime UI.",
  alternates: { canonical: "/tldr" },
};

const lifecycle = ["REFLEXING", "READY", "RECALL", "WATCH", "VERIFY", "REMEMBER"];

const evidence = [
  ["Repository structure", "Paths, roles, manifests and project topology are structural priors."],
  ["Symbols + dependencies", "Top-level symbol names and declared dependencies improve cold-start localisation."],
  ["Git history", "Hotspots and bounded co-change relationships add a small structural signal."],
  ["Observed execution", "Known task outcomes reinforce the files and paths that actually mattered."],
  ["Verified execution", "Explicitly verified success is the strongest reusable evidence."],
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-[0.72rem] uppercase tracking-[0.16em] text-accent">{children}</p>;
}

function FactCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="border border-line bg-panel/45 p-5 sm:p-6">
      <h3 className="font-serif text-[1.25rem] text-ink">{title}</h3>
      <div className="mt-3 text-[0.95rem] leading-7 text-muted">{children}</div>
    </article>
  );
}

export default function TldrPage() {
  return (
    <>
      <Navbar showViewToggle={false} />
      <main>
        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-16 sm:px-10 sm:py-24">
            <SectionLabel>OpenReflex / TLDR</SectionLabel>
            <h1 className="mt-5 max-w-[850px] font-serif text-[2.8rem] leading-[1.02] tracking-[-0.02em] text-ink sm:text-[4.2rem]">
              A coding agent should not pay the full exploration cost twice.
            </h1>
            <p className="mt-7 max-w-[760px] text-[1.08rem] leading-8 text-muted">
              OpenReflex is local muscle memory for AI coding agents. It learns the structure of a project without blocking the developer, observes how work is actually completed, closes tasks against verification evidence, and gives later tasks a smaller, better starting context. The aim is not to replay an old trajectory. It is to reduce unnecessary rereading, retries, tool calls and context while preserving verified task completion.
            </p>

            <div className="mt-9 flex flex-wrap gap-3">
              <a
                href="/#quickstart"
                className="inline-flex h-11 items-center rounded-md bg-ink px-5 text-[0.94rem] font-medium text-bg"
              >
                Install OpenReflex
              </a>
              <a
                href={LINKS.github}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-11 items-center rounded-md border border-line-strong px-5 text-[0.94rem] text-ink transition-colors hover:bg-panel"
              >
                View source
              </a>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>The problem</SectionLabel>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <FactCard title="Agents forget the project">
                New sessions often rediscover repository structure, reread the same files and reconstruct the same local context.
              </FactCard>
              <FactCard title="Success can still be wasteful">
                A task can finish correctly after avoidable searches, failed commands, oversized context and unnecessary retries.
              </FactCard>
              <FactCard title="Raw traces are not memory">
                Saving every transcript or replaying whole trajectories creates noise. OpenReflex keeps bounded, provenance-aware evidence instead.
              </FactCard>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>The loop</SectionLabel>
            <h2 className="mt-4 max-w-[760px] font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
              Understand the project, retrieve only what matters, verify the outcome, then reinforce useful evidence.
            </h2>

            <div className="mt-9 overflow-x-auto border-y border-line py-5">
              <div className="flex min-w-[760px] items-center justify-between gap-2 font-mono text-[0.78rem] tracking-[0.08em] text-ink">
                {lifecycle.map((item, index) => (
                  <div key={item} className="flex flex-1 items-center gap-2">
                    <span className="border border-line-strong bg-bg px-3 py-2">{item}</span>
                    {index < lifecycle.length - 1 && <span className="text-muted">→</span>}
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <FactCard title="Project Primer">
                Starts in a detached worker so Claude does not wait for repository understanding. It builds bounded project memory and refreshes stale facts without putting Git, SQLite or indexing work on the statusline path.
              </FactCard>
              <FactCard title="ReflexIndex">
                Combines structural project memory with execution evidence. Unknown outcomes do not train it. Repeated Stop/SessionEnd events cannot double-count an execution, and later explicit verification upgrades confidence rather than inventing a second run.
              </FactCard>
              <FactCard title="Outcome closure">
                If edited work has not been verified, OpenReflex can request one verification continuation. Unknown outcomes are shown as UNVERIFIED, failures as FAILED, and only known successful outcomes as COMPLETE. Regret is never shown for an unknown outcome.
              </FactCard>
              <FactCard title="Statusline + TUI">
                The Claude statusline reads cached state only and follows live PreToolUse activity. The optional TUI exposes lifecycle, project-memory health, versions, known outcomes, verified outcomes and the evidence OpenReflex has accumulated.
              </FactCard>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>Work modes / 0.5.0</SectionLabel>
            <div className="mt-5 grid gap-8 lg:grid-cols-[1fr_1fr]">
              <div>
                <h2 className="font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
                  BUILD, INVESTIGATE and THINK are different jobs. OpenReflex stops treating them the same.
                </h2>
                <p className="mt-5 text-[1rem] leading-8 text-muted">
                  Coding tasks still get inspect-first, test-first and incremental paths. Investigation gets its own
                  paths — source-first, cross-check, broad-then-deep — and reasoning gets reason-first,
                  compare-options and evidence-first. Substantive zero-tool reasoning and investigation now count as
                  real executions, and recommendations stay separate from observed paths so OpenReflex never claims a
                  suggested path ran when it was not actually observed.
                </p>
                <p className="mt-4 text-[1rem] leading-8 text-muted">
                  A /loop or scheduled or background task now shows WAITING instead of being finalised early, and
                  resumes the same execution when the next matching scheduled iteration runs. The confusing numeric
                  comparison language is gone: the runtime shows a plain Path check, either a better option backed by
                  comparable completed tasks, or none proven.
                </p>
              </div>

              <div className="border border-line bg-term p-5 font-mono text-[0.78rem] leading-7 text-term-text sm:p-6">
                <div className="text-term-dim">Claude statusline</div>
                <div className="mt-2 text-accent">↺ OpenReflex v0.5.0  INVESTIGATE</div>
                <div>project · READ README.md · 4 calls · 8.3k tokens</div>
                <div className="mt-3 text-accent">↺ OpenReflex v0.5.0  THINK</div>
                <div>project · reasoning · 0 calls · 4.2k tokens</div>
                <div className="mt-3 text-accent">↺ OpenReflex v0.5.0  WAITING</div>
                <div>project · 1 scheduled</div>
                <div className="mt-3 text-term-dim">completion</div>
                <div>success · cross-check</div>
                <div>7 calls · 18.2k model tokens · 2.5m</div>
                <div>Path check · better option: none proven</div>
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <FactCard title="Real model-token accounting">
                An opt-in local receiver on 127.0.0.1:4319 reads Claude Code's documented api_request OpenTelemetry
                data and stores input, output, cache-read and cache-creation token counts, model and main/subagent
                source, and estimated cost. Prompts, responses, thinking, tool arguments and raw API bodies are never
                collected.
              </FactCard>
              <FactCard title="Token samples, not a schema rewrite">
                Token samples live in their own table alongside the existing Experience Graph database, so a 0.4.x
                project upgrades without rewriting existing graph nodes. The status line and TUI show real model
                tokens when available, and legacy tool-output estimates stay labelled separately rather than being
                mixed in.
              </FactCard>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>Runtime / 0.4.1</SectionLabel>
            <div className="mt-5 grid gap-8 lg:grid-cols-[1fr_1fr]">
              <div>
                <h2 className="font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
                  The line in Claude should say what OpenReflex is doing now.
                </h2>
                <p className="mt-5 text-[1rem] leading-8 text-muted">
                  OpenReflex tracks tool start and completion separately. The statusline can therefore show safe coarse activity such as READ, SEARCH, EDIT, TEST, LINT, BUILD, GIT, WEB, MCP or RUN while a task is active, instead of only showing a generic completed-call count.
                </p>
                <p className="mt-4 text-[1rem] leading-8 text-muted">
                  Project-relative file targets may be shown, but raw shell commands are never echoed into the statusline. A new task resets previous call/activity state, and an active task moves from RECALL to WATCH rather than looking READY while Claude is still working.
                </p>
              </div>

              <div className="border border-line bg-term p-5 font-mono text-[0.78rem] leading-7 text-term-text sm:p-6">
                <div className="text-term-dim">Claude statusline</div>
                <div className="mt-2 text-accent">↺ OpenReflex v0.4.1  RECALL</div>
                <div>3 related · inspect-first</div>
                <div className="mt-3 text-accent">↺ OpenReflex v0.4.1  WATCH</div>
                <div>READ charts/app/values.yaml · 4 calls</div>
                <div className="mt-3 text-accent">↺ OpenReflex v0.4.1  VERIFY</div>
                <div>LINT · 5 calls</div>
                <div className="mt-3 text-term-dim">completion</div>
                <div>success → COMPLETE</div>
                <div>failure → FAILED</div>
                <div>unknown → UNVERIFIED</div>
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <FactCard title="Reload-aware versions">
                Claude plugin, OpenReflex package and MCP runtime versions are tracked separately. Reloading plugins can therefore prove which plugin/MCP version became active instead of assuming the whole stack updated together.
              </FactCard>
              <FactCard title="Mismatch is visible">
                If Claude loads a newer plugin but the executable or MCP runtime is stale, the TUI reports VERSION MISMATCH. Matching package, plugin and MCP versions report ALIGNED.
              </FactCard>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>Project Map / 0.4.0</SectionLabel>
            <div className="mt-5 grid gap-8 lg:grid-cols-[1.05fr_0.95fr]">
              <div>
                <h2 className="font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
                  Cold-start memory without turning the repository into a giant vector dump.
                </h2>
                <p className="mt-5 text-[1rem] leading-8 text-muted">
                  Project Map indexes tracked paths, file roles, languages, lightweight top-level symbol names, declared dependencies, Git hotspots and bounded co-change relationships. Nested Helm, Node, Python, Go and Rust manifests are indexed with project-relative provenance, which matters for monorepos and multi-chart repositories.
                </p>
                <p className="mt-4 text-[1rem] leading-8 text-muted">
                  Source bodies are read transiently where needed for extraction but are not persisted in the structural map. Retrieval mixes path and symbol overlap with small structural signals and stronger observed execution support. Verified execution remains more authoritative than repository history.
                </p>
              </div>

              <div className="border border-line bg-term p-5 font-mono text-[0.78rem] leading-7 text-term-text sm:p-6">
                <div className="text-term-dim">task</div>
                <div>↓</div>
                <div>path + identifier match</div>
                <div>↓</div>
                <div>dependency + role signal</div>
                <div>↓</div>
                <div>hotspot + co-change prior</div>
                <div>↓</div>
                <div className="text-accent">observed execution support</div>
                <div>↓</div>
                <div className="text-accent">verified execution support</div>
                <div>↓</div>
                <div>bounded task context</div>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>Evidence hierarchy</SectionLabel>
            <h2 className="mt-4 max-w-[780px] font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
              OpenReflex separates what the repository suggests from what executions actually proved.
            </h2>

            <div className="mt-8 divide-y divide-line border-y border-line">
              {evidence.map(([title, body], index) => (
                <div key={title} className="grid gap-2 py-5 sm:grid-cols-[44px_220px_1fr] sm:items-start">
                  <span className="font-mono text-[0.75rem] text-accent">0{index + 1}</span>
                  <h3 className="font-medium text-ink">{title}</h3>
                  <p className="text-[0.94rem] leading-7 text-muted">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>Privacy boundary</SectionLabel>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <FactCard title="Local by default">
                Project memory lives in the existing per-project OpenReflex store on the developer machine. The workflow remains: install OpenReflex, start the coding agent, work normally.
              </FactCard>
              <FactCard title="Derived metadata, not a transcript archive">
                Project Map persists project-relative paths, roles, symbol names, dependency names, fingerprints and aggregate Git signals. It does not persist raw source bodies, diffs, command output or agent transcripts in the structural map. Plugin cache paths are not persisted by version diagnostics.
              </FactCard>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>What exists in 0.5.0</SectionLabel>
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <FactCard title="Managed project memory">
                Non-blocking Project Primer, provenance-aware project facts, staleness handling, bounded retrieval and explicit separation between structural priors and execution evidence.
              </FactCard>
              <FactCard title="Verified execution memory">
                Outcome closure, verification-aware reinforcement, unknown-outcome non-training, idempotent evidence updates, Helm/Kubernetes verification and corrected reuse-rate semantics.
              </FactCard>
              <FactCard title="Indexed Project Map">
                Paths, symbols, nested manifests, dependencies, hotspots and co-change relationships feed compact cold-start context while the statusline and TUI stay cache-only on their render path.
              </FactCard>
              <FactCard title="Truthful runtime UI">
                Live operation state, accurate COMPLETE / FAILED / UNVERIFIED semantics, reload-aware package/plugin/MCP versions, ALIGNED or VERSION MISMATCH diagnostics, and per-task call/activity reset.
              </FactCard>
              <FactCard title="Work modes beyond coding">
                BUILD, INVESTIGATE and THINK paths, substantive zero-tool reasoning and investigation counted as real executions, and a plain Path check instead of numeric regret comparisons.
              </FactCard>
              <FactCard title="Real token accounting">
                Opt-in local Claude Code token accounting from documented OpenTelemetry data, stored in its own schema-v2 table so existing 0.4.x databases migrate without rewriting graph nodes.
              </FactCard>
            </div>

            <div className="mt-7 flex flex-wrap gap-3 text-[0.9rem]">
              <a
                href={`${LINKS.github}/pull/16`}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-line px-4 py-2 text-ink transition-colors hover:bg-panel"
              >
                Core memory PR #16
              </a>
              <a
                href={`${LINKS.github}/pull/17`}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-line px-4 py-2 text-ink transition-colors hover:bg-panel"
              >
                Project Map PR #17
              </a>
              <a
                href={`${LINKS.github}/pull/20`}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-line px-4 py-2 text-ink transition-colors hover:bg-panel"
              >
                Completion semantics PR #20
              </a>
              <a
                href={`${LINKS.github}/pull/21`}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-line px-4 py-2 text-ink transition-colors hover:bg-panel"
              >
                Live TUI PR #21
              </a>
              <a
                href={`${LINKS.github}/pull/24`}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-line px-4 py-2 text-ink transition-colors hover:bg-panel"
              >
                Work modes + tokens PR #24
              </a>
            </div>
          </div>
        </section>

        <section>
          <div className="mx-auto max-w-[1120px] px-5 py-14 sm:px-10 sm:py-20">
            <SectionLabel>The measurement that matters</SectionLabel>
            <h2 className="mt-4 max-w-[800px] font-serif text-[2.2rem] leading-tight text-ink sm:text-[3rem]">
              Past work should measurably improve future work.
            </h2>
            <p className="mt-5 max-w-[800px] text-[1rem] leading-8 text-muted">
              OpenReflex carries a deterministic cold-start CI benchmark for target-file localisation, target rank, nested-manifest evidence, structural-evidence labelling and injected-context size. It is intentionally model-free: passing it proves the Project Map retrieval contract, not causal token or time savings.
            </p>
            <p className="mt-4 max-w-[800px] text-[1rem] leading-8 text-muted">
              The next evidence layer is live-agent evaluation: compare exploration and search calls, tool calls, context tokens, elapsed time and verified completion on matched tasks. That is the standard required before claiming real efficiency gains.
            </p>

            <div className="mt-9 border-l-2 border-accent pl-5 sm:pl-7">
              <p className="font-serif text-[1.55rem] leading-9 text-ink">
                OpenReflex is not trying to make an agent agree with its memory. It is trying to make useful prior evidence reduce the cost of the next correct execution.
              </p>
            </div>

            <div className="mt-10 flex flex-wrap gap-3">
              <a
                href="/"
                className="inline-flex h-11 items-center rounded-md bg-ink px-5 text-[0.94rem] font-medium text-bg"
              >
                Back to OpenReflex
              </a>
              <a
                href="/?view=research"
                className="inline-flex h-11 items-center rounded-md border border-line-strong px-5 text-[0.94rem] text-ink transition-colors hover:bg-panel"
              >
                Read the research view
              </a>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
