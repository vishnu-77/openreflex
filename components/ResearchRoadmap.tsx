import { SectionHeader } from "./SectionHeader";

const BUMPS = [
  {
    index: "01",
    status: "IMPLEMENTATION FOUNDATION",
    title: "Observable, configurable execution intelligence",
    intro:
      "Establish a durable product contract: one policy drives routing, runtime control, scoring and visibility; every consequential recommendation is persisted and explainable.",
    items: [
      ["Versioned execution policy", "Move tunable priors, objective weights, budgets, thresholds, visibility rules and strategy templates out of Python literals and into a validated policy with user/project overrides."],
      ["Canonical execution state", "Represent task, path, progress, failures, context, budget, uncertainty and historical evidence as the shared state consumed by routing and control."],
      ["DecisionSnapshot", "Persist the recommendation, alternatives, score, confidence, evidence quality, route edge, token cost, budget pressure and reason codes behind each decision."],
      ["Reflex Score", "Produce a deterministic, decomposable 0–100 strength-of-recommendation score. Keep it separate from estimated task-success probability."],
      ["Evidence quality + stability", "Distinguish strong comparable verified runs from weak matches, and record whether the winning route is clearly ahead or almost tied with the alternative."],
      ["Compute accounting", "Separate OpenReflex context overhead from agent/tool execution cost: context tokens, tool calls, wall time, output tokens and compactions."],
      ["Visibility policy", "Show one start recap, stay ambient during healthy execution, surface material pivot/stop/budget events, and close with a completion recap."],
      ["Explainability surfaces", "Expose the same evidence through `openreflex why`, `openreflex trace` and MCP decision/trace/score tools instead of reconstructing an explanation later."],
      ["Compatible persistence", "Store decision history with the execution so existing local databases remain usable and later policy versions can be evaluated against the decisions they produced."],
    ],
  },
  {
    index: "02",
    status: "RESEARCH DIRECTION",
    title: "Adaptive execution policy + project muscle memory",
    intro:
      "Move from a configurable router to a project-adapted sequential policy that learns how this codebase is best worked on and allocates context, tools and inference-time compute accordingly.",
    items: [
      ["Unified sequential policy", "Evaluate continue, retrieve, inject context, compress, inspect, verify, pivot and stop as competing actions under the same resource-constrained objective."],
      ["Value-of-information context", "Rank memories by expected change in execution utility minus token cost, redundancy and stale evidence rather than by similarity alone."],
      ["Inference-time compute allocation", "Treat model/tool tokens, tool calls, wall time, context growth and repeated exploration as compute; continue only while expected marginal value remains positive."],
      ["Execution phase inference", "Infer orient → explore → hypothesise → act → verify → resolve and detect pathological transitions such as endless exploration, repeated failed action or implementation without verification."],
      ["Strategy discovery", "Extract recurring successful phase/tool sequences and promote well-supported project-specific procedures instead of permanently limiting routing to hand-authored strategies."],
      ["Project calibration", "Learn task-class priors, strategy cost distributions, failure likelihoods, context value and pivot sensitivity from completed local trajectories with sample count and confidence metadata."],
      ["Counterfactual evaluation", "Compare the realised path with plausible alternatives, estimate when a switch would have been useful and use Execution Regret as feedback rather than as a decorative metric."],
      ["Context ROI", "Once matched evidence is sufficient, estimate whether a small context injection is historically associated with lower execution waste. Do not claim saved tokens without evidence."],
      ["Policy replay", "Replay historical trajectories against candidate policy versions and promote only policies that improve declared success/cost/regret objectives without destabilising behaviour."],
      ["Calibrated uncertainty", "Report confidence intervals or confidence bands, condition priors on agent/model/tooling where justified, and calibrate Reflex Score against observed recommendation quality."],
      ["Adaptive context lifecycle", "Retain, replace, compress or drop context as its marginal value changes during the task rather than treating injected memory as permanently useful."],
    ],
  },
];

export function ResearchRoadmap() {
  return (
    <section id="roadmap" aria-labelledby="roadmap-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="roadmap"
          title="Two bumps, one execution-policy thesis"
          intro="The roadmap deliberately separates a maintainable observability foundation from the harder learning problem. Bump 1 makes decisions configurable and inspectable. Bump 2 tests whether longitudinal project experience can become a calibrated execution policy rather than a collection of heuristics."
        />

        <div className="mt-10 grid gap-8 xl:grid-cols-2">
          {BUMPS.map((bump) => (
            <article key={bump.index} className="border border-line bg-panel">
              <header className="border-b border-line p-6 sm:p-8">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="font-mono text-sm tabular-nums text-accent">BUMP {bump.index}</span>
                  <span className="border border-line-strong px-3 py-1 font-mono text-[0.68rem] tracking-[0.12em] text-muted">
                    {bump.status}
                  </span>
                </div>
                <h3 className="mt-5 max-w-[34rem] font-serif text-[1.8rem] leading-tight text-ink sm:text-[2.1rem]">
                  {bump.title}
                </h3>
                <p className="mt-4 max-w-[40rem] leading-7 text-muted">{bump.intro}</p>
              </header>

              <ol className="divide-y divide-line">
                {bump.items.map(([name, body], index) => (
                  <li key={name} className="grid gap-3 p-6 sm:grid-cols-[2.3rem_minmax(0,1fr)] sm:p-7">
                    <span className="font-mono text-[0.72rem] tabular-nums text-muted">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h4 className="font-semibold tracking-tight text-ink">{name}</h4>
                      <p className="mt-2 leading-7 text-muted">{body}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>

        <div className="mt-12 border border-line bg-panel p-6 sm:p-8">
          <p className="font-mono text-[0.72rem] uppercase tracking-[0.15em] text-accent">SYSTEM BOUNDARY</p>
          <div className="mt-5 grid gap-px overflow-hidden border border-line bg-line md:grid-cols-5">
            {[
              ["HARNESS", "Observe actual execution"],
              ["STATE", "Represent the task now"],
              ["POLICY", "Evaluate competing actions"],
              ["DECISION", "Persist evidence + rationale"],
              ["LEARNING", "Update future priors"],
            ].map(([title, body]) => (
              <div key={title} className="bg-bg-soft p-5">
                <p className="font-mono text-[0.68rem] tracking-[0.12em] text-accent">{title}</p>
                <p className="mt-2 text-sm leading-6 text-text">{body}</p>
              </div>
            ))}
          </div>
          <p className="mt-5 max-w-[60rem] text-sm leading-6 text-muted">
            Harness, context engineering, inference-time compute and routing are not separate product modes. They are
            inputs and actions around one constrained execution policy. The policy decides; the snapshot records; the
            recap, CLI, MCP and visual researcher surfaces render that same decision.
          </p>
        </div>
      </div>
    </section>
  );
}
