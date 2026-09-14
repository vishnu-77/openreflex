import { SectionHeader } from "./SectionHeader";

const STATES = [
  {
    label: "TASK START",
    tone: "text-accent",
    headline: "↺ OpenReflex · 82",
    lines: [
      "4 experiences · test-first 71%",
      "~23 calls · ~18k tokens · +186 context tokens",
    ],
    note: "Visible once when a substantial task begins.",
  },
  {
    label: "MATERIAL CHANGE",
    tone: "text-signal",
    headline: "↺ OpenReflex · 64 ↓18",
    lines: [
      "11/23 calls · 2 failures · confidence 71→52%",
      "inspect-first now leads · recommendation → pivot",
    ],
    note: "Visible only when the execution policy materially changes its recommendation.",
  },
  {
    label: "COMPLETION",
    tone: "text-accent",
    headline: "↺ OpenReflex · COMPLETE",
    lines: [
      "success · test-first",
      "18 calls · 14.2k tokens · 6.4m",
      "regret 0.05 vs inspect-first",
    ],
    note: "Closes the visible loop with realised path, observed cost and comparison route. Reusable lessons are stored immediately after completion.",
  },
];

const CHANNELS = [
  {
    channel: "Ambient",
    claude: "additionalContext",
    user: "Silent",
    use: "Retrieved experience, likely files, normal execution guidance",
  },
  {
    channel: "Recap",
    claude: "additionalContext",
    user: "systemMessage",
    use: "Task start and completion",
  },
  {
    channel: "Intervention",
    claude: "additionalContext",
    user: "systemMessage",
    use: "Pivot, stop, budget pressure, failure loop or material degradation",
  },
];

export function ReflexRecap() {
  return (
    <section id="recap" aria-labelledby="recap-title" className="border-b border-line bg-bg">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="recap"
          title="A visible execution recap, without a noisy agent"
          intro="OpenReflex separates what the coding agent needs to know from what the developer needs to see. Routine guidance stays in the agent context; only the start, a consequential policy change, and completion become compact user-facing recaps."
        />

        <div className="mt-10 border border-line bg-panel">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-7">
            <div>
              <p className="font-mono text-[0.72rem] uppercase tracking-[0.16em] text-muted">Execution recap · v0.3</p>
              <p className="mt-1 text-sm text-text">Plan → observe → intervene → learn.</p>
            </div>
            <span className="border border-line-strong px-3 py-1 font-mono text-[0.72rem] text-muted">Claude Code</span>
          </div>

          <div className="grid gap-px bg-line lg:grid-cols-3">
            {STATES.map((state) => (
              <article key={state.label} className="bg-panel p-6 sm:p-7">
                <div className={`font-mono text-[0.72rem] uppercase tracking-[0.15em] ${state.tone}`}>{state.label}</div>
                <div className="mt-6 border-y border-line py-5 font-mono">
                  <p className="text-[1.12rem] font-semibold tracking-tight text-ink">{state.headline}</p>
                  <div className="mt-3 space-y-1 text-[0.86rem] leading-6 text-text">
                    {state.lines.map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </div>
                </div>
                <p className="mt-5 text-sm leading-6 text-muted">{state.note}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-12 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.72fr)]">
          <div className="overflow-hidden border border-line bg-panel">
            <div className="border-b border-line px-5 py-4 sm:px-6">
              <h3 className="font-semibold tracking-tight text-ink">Visibility contract</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] border-collapse text-left text-sm">
                <thead className="bg-muted-bg font-mono text-[0.7rem] uppercase tracking-[0.12em] text-muted">
                  <tr>
                    <th className="border-b border-line px-5 py-3 font-medium">Mode</th>
                    <th className="border-b border-line px-5 py-3 font-medium">Claude receives</th>
                    <th className="border-b border-line px-5 py-3 font-medium">Developer sees</th>
                    <th className="border-b border-line px-5 py-3 font-medium">Used for</th>
                  </tr>
                </thead>
                <tbody>
                  {CHANNELS.map((row) => (
                    <tr key={row.channel} className="border-b border-line last:border-b-0">
                      <td className="px-5 py-4 font-semibold text-ink">{row.channel}</td>
                      <td className="px-5 py-4 font-mono text-[0.8rem] text-accent">{row.claude}</td>
                      <td className="px-5 py-4 text-text">{row.user}</td>
                      <td className="px-5 py-4 leading-6 text-muted">{row.use}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="border border-line bg-panel p-6 sm:p-7">
            <p className="font-mono text-[0.72rem] uppercase tracking-[0.15em] text-accent">REFLEX SCORE</p>
            <div className="mt-5 flex items-end gap-3 border-b border-line pb-5">
              <span className="font-serif text-6xl leading-none text-ink">82</span>
              <span className="pb-1 font-mono text-sm text-muted">/ 100</span>
            </div>
            <p className="mt-5 leading-7 text-text">
              A Reflex Score describes the strength of the recommendation, not the probability that the task will
              succeed. It is decomposable into evidence, confidence, route separation, budget fit and relevance.
            </p>
            <dl className="mt-6 grid gap-3 font-mono text-[0.78rem]">
              {[
                ["evidence", "88"],
                ["confidence", "76"],
                ["route edge", "81"],
                ["budget fit", "94"],
                ["relevance", "73"],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between border-t border-line pt-3">
                  <dt className="text-muted">{label}</dt>
                  <dd className="tabular-nums text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-6 text-sm leading-6 text-muted">
              The implementation reads score weights and thresholds from a versioned execution policy rather than from
              presentation code. The same snapshot powers the recap, CLI, MCP and future visualisation surfaces.
            </p>
          </aside>
        </div>
      </div>
    </section>
  );
}
