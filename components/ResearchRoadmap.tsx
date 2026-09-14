import { SectionHeader } from "./SectionHeader";

type Stage = {
  version: string;
  status: string;
  title: string;
  question: string;
  hypothesis: string;
  mechanism: string[];
  evaluation: string[];
  note?: string;
};

const STAGES: Stage[] = [
  {
    version: "v0.2",
    status: "RELEASED FOUNDATION",
    title: "Execution memory and trajectory evidence",
    question: "Can local lifecycle telemetry become useful execution memory without storing raw transcripts or code contents?",
    hypothesis:
      "A project-local Experience Graph can preserve enough structure about tasks, tools, outcomes and resolutions to improve later execution decisions while remaining privacy-minimised.",
    mechanism: [
      "Lifecycle hooks and MCP capture task, tool category, status, project-relative files and verification outcomes.",
      "Experience Graph nodes connect tasks, candidate paths, executions, tool calls, outcomes and lessons.",
      "Similar prior executions are retrieved and converted into advisory context for the next task.",
      "Execution Regret compares the realised route with plausible alternatives when outcome evidence is available.",
    ],
    evaluation: [
      "Experience reuse rate",
      "Routing agreement",
      "Known-outcome success rate",
      "Execution Regret coverage and trend",
      "Privacy and project-boundary correctness",
    ],
  },
  {
    version: "v0.3",
    status: "CURRENT",
    title: "Observable, configurable execution policy",
    question: "Can execution recommendations be made decomposable, reproducible and inspectable rather than hidden in ad-hoc routing logic?",
    hypothesis:
      "A versioned policy plus persistent decision snapshots can make route selection, budget use and runtime intervention explainable without changing the agent's normal workflow.",
    mechanism: [
      "Versioned TOML policy controls routing objectives, priors, budgets, detectors, scoring and visibility.",
      "DecisionSnapshot records the chosen route, alternatives, confidence, evidence quality, route edge, budget pressure and context overhead.",
      "Reflex Score describes recommendation strength separately from estimated task-success probability.",
      "Claude Code receives compact start/intervention/completion recaps; all agents continue to receive protocol-appropriate execution context.",
      "`openreflex why`, `openreflex trace` and MCP tools expose the same stored decision evidence.",
    ],
    evaluation: [
      "Decision stability",
      "Score decomposition consistency",
      "Context overhead",
      "Budget adherence",
      "Pivot/stop precision",
      "Cross-agent lifecycle compatibility",
    ],
    note: "This is the current implementation line. Tunable decision values live in the execution policy rather than presentation code.",
  },
  {
    version: "v0.4",
    status: "ACTIVE RESEARCH",
    title: "Adaptive project execution policy",
    question: "Can repeated project trajectories teach OpenReflex how this codebase is best worked on rather than relying on permanently hand-authored strategies?",
    hypothesis:
      "Project-specific priors, phase patterns and strategy statistics should outperform generic routing once enough comparable verified executions exist.",
    mechanism: [
      "Infer execution phases: orient → explore → hypothesise → act → verify → resolve.",
      "Discover recurring successful phase/tool sequences and promote supported project-specific strategies.",
      "Calibrate strategy success, expected cost, failure likelihood and pivot sensitivity from completed local trajectories.",
      "Evaluate continue, retrieve, inspect, verify, pivot and stop as competing actions under one constrained execution policy.",
    ],
    evaluation: [
      "Held-out task success",
      "Tool-call and token efficiency",
      "Phase-transition quality",
      "Regret reduction",
      "Calibration error",
      "Project-specific strategy support",
    ],
  },
  {
    version: "v0.5",
    status: "FUTURE RESEARCH",
    title: "Inference and context economics",
    question: "Can OpenReflex allocate context and inference-time compute according to expected marginal value rather than fixed retrieval and execution budgets?",
    hypothesis:
      "Value-of-information context selection and counterfactual policy replay can reduce wasted computation while preserving or improving task success.",
    mechanism: [
      "Score candidate memories by expected utility change minus token cost, redundancy and stale evidence.",
      "Treat tokens, tool calls, wall time, context growth and repeated exploration as execution compute.",
      "Retain, replace, compress or drop context as its marginal value changes during the task.",
      "Replay historical trajectories against candidate policy versions before promotion.",
      "Calibrate Reflex Score and confidence bands against observed recommendation quality.",
    ],
    evaluation: [
      "Context ROI with confidence bounds",
      "Marginal compute efficiency",
      "Counterfactual regret",
      "Policy replay win rate",
      "Calibration curves",
      "Task success under matched budgets",
    ],
  },
];

export function ResearchRoadmap() {
  return (
    <section id="roadmap" aria-labelledby="roadmap-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="roadmap"
          title="Research roadmap"
          intro="From execution memory to an adaptive execution policy. Each version states the research question, falsifiable hypothesis, mechanism and evaluation criteria so shipped behaviour stays distinct from future claims."
        />

        <div className="mt-10 border border-line bg-panel">
          {STAGES.map((stage, index) => (
            <details key={stage.version} open={stage.version === "v0.3"} className="group border-b border-line last:border-b-0">
              <summary className="grid cursor-pointer list-none gap-4 p-5 marker:hidden sm:grid-cols-[5.5rem_minmax(0,1fr)_auto] sm:items-center sm:p-7 [&::-webkit-details-marker]:hidden">
                <span className="font-mono text-sm font-semibold tabular-nums text-accent">{stage.version}</span>
                <div>
                  <h3 className="font-semibold tracking-tight text-ink">{stage.title}</h3>
                  <p className="mt-1 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-muted">{stage.status}</p>
                </div>
                <span className="font-mono text-lg text-muted transition-transform group-open:rotate-45" aria-hidden="true">
                  +
                </span>
              </summary>

              <div className="border-t border-line bg-bg px-5 py-7 sm:px-7 sm:py-8">
                <div className="grid gap-8 xl:grid-cols-2">
                  <div className="space-y-7">
                    <div>
                      <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Research question</p>
                      <p className="mt-3 max-w-[42rem] font-serif text-[1.35rem] leading-8 text-ink">{stage.question}</p>
                    </div>
                    <div>
                      <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Hypothesis</p>
                      <p className="mt-3 max-w-[42rem] leading-7 text-text">{stage.hypothesis}</p>
                    </div>
                    {stage.note && (
                      <p className="border-l-2 border-accent pl-4 text-sm leading-6 text-muted">{stage.note}</p>
                    )}
                  </div>

                  <div className="grid gap-7 sm:grid-cols-2">
                    <div>
                      <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Mechanism</p>
                      <ol className="mt-4 space-y-3">
                        {stage.mechanism.map((item, itemIndex) => (
                          <li key={item} className="grid grid-cols-[1.8rem_minmax(0,1fr)] gap-2 text-sm leading-6 text-text">
                            <span className="font-mono text-[0.68rem] tabular-nums text-muted">
                              {String(itemIndex + 1).padStart(2, "0")}
                            </span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                    <div>
                      <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Evaluation</p>
                      <ul className="mt-4 space-y-3">
                        {stage.evaluation.map((item) => (
                          <li key={item} className="border-t border-line pt-3 text-sm leading-6 text-text first:border-t-0 first:pt-0">
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </details>
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
            Harness engineering, context engineering, inference-time compute and routing are not separate product modes.
            They are observations, resources and actions around one constrained execution policy. The policy decides;
            the snapshot records; the recap, CLI, MCP and researcher surfaces render that same decision.
          </p>
        </div>
      </div>
    </section>
  );
}
