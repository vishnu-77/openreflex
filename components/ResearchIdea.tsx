import { SectionHeader } from "./SectionHeader";

const LOOP = [
  {
    name: "Retrieve",
    body: "Retrieve comparable verified executions from the project-local Experience Graph.",
  },
  {
    name: "Select",
    body: "Estimate candidate execution paths under success, cost, risk, uncertainty and reversibility constraints.",
  },
  {
    name: "Control",
    body: "Observe execution progress and estimate whether continuing, pivoting or stopping has higher expected utility.",
  },
  {
    name: "Learn",
    body: "Persist verified outcomes and estimated execution regret to update later path priors.",
  },
];

export function ResearchIdea() {
  return (
    <section id="idea" aria-labelledby="idea-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="idea"
          title="Execution intelligence for coding agents"
          intro="OpenReflex studies whether evidence from prior executions can help coding agents use computation more deliberately during a task. This page documents only research ideas that are already represented in public releases."
        />

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Research question</p>
            <p className="mt-4 max-w-[48rem] font-serif text-[1.45rem] leading-9 text-ink">
              Can verified execution experience improve how a coding agent chooses a path, spends its budget and responds when progress deteriorates?
            </p>
          </div>
          <div className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Claim boundary</p>
            <p className="mt-4 leading-7 text-text">
              Public claims are limited to behaviour and evidence present in tagged OpenReflex releases. Unreleased methods,
              experiments and research directions are intentionally not described here.
            </p>
          </div>
        </div>

        <h3 className="mt-14 text-[1.2rem] font-semibold tracking-tight text-ink">Released execution loop</h3>
        <ol className="mt-5 grid gap-px overflow-hidden border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {LOOP.map((step, index) => (
            <li key={step.name} className="bg-panel p-5 sm:p-6">
              <span className="font-mono text-[0.72rem] tabular-nums text-accent">{String(index + 1).padStart(2, "0")}</span>
              <h4 className="mt-3 font-semibold tracking-tight text-ink">{step.name}</h4>
              <p className="mt-2 text-sm leading-6 text-muted">{step.body}</p>
            </li>
          ))}
        </ol>

        <p className="mt-8 max-w-[64rem] text-sm leading-7 text-muted">
          The developer-facing idea remains simple: useful execution memory should make the agent feel more effective. The
          researcher view exists to document what has been released, how it is measured and where its claims sit relative to prior work.
        </p>
      </div>
    </section>
  );
}
