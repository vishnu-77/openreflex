import { SectionHeader } from "./SectionHeader";

type Stage = {
  version: string;
  status: string;
  title: string;
  objective: string;
  change: string[];
  gate: string[];
  note?: string;
};

const STAGES: Stage[] = [
  {
    version: "v0.3",
    status: "CURRENT",
    title: "Observable execution policy",
    objective: "Preserve the current product baseline before changing the learning model.",
    change: [
      "Versioned routing policy, execution budgets and continue / pivot / stop advisories remain the default behaviour.",
      "Decision snapshots, `why`, `trace` and existing MCP / hook integrations remain backward compatible.",
    ],
    gate: ["Current test suite remains green", "No migration required for existing project memory"],
    note: "vNext is additive. Existing users should not experience a behaviour change merely because research instrumentation lands.",
  },
  {
    version: "v0.3.1",
    status: "NEXT — MEASUREMENT",
    title: "Execution-state evidence",
    objective: "Make every intervention decision reproducible before attempting to learn one.",
    change: [
      "Add a stable, privacy-minimised ExecutionState snapshot at decision points.",
      "Separate observed evidence, heuristic estimates and verified outcomes in persisted records.",
      "Rename causal-sounding metrics where only estimated alternatives are available.",
    ],
    gate: ["Deterministic decision replay", "No raw transcript or tool-output storage", "No change to intervention policy"],
  },
  {
    version: "v0.3.2",
    status: "SHADOW MODE",
    title: "Outcome and intervention dataset",
    objective: "Collect learning-ready examples without allowing learned predictions to affect the agent.",
    change: [
      "Derive compact trajectory-prefix features from existing lifecycle events.",
      "Record candidate actions and verified downstream utility where it is observable.",
      "Introduce dataset export for controlled research runs only.",
    ],
    gate: ["Schema stability", "Project isolation", "Feature coverage across at least two supported harnesses"],
  },
  {
    version: "v0.4",
    status: "RESEARCH HARNESS",
    title: "Matched-prefix branch evaluation",
    objective: "Replace guessed alternatives with realised outcomes during offline experiments.",
    change: [
      "Create reproducible repository snapshots at selected intervention points.",
      "Run matched continue / pivot / stop branches from the same prefix in an isolated benchmark harness.",
      "Measure task success and execution utility under identical task state and evaluation criteria.",
    ],
    gate: ["Branch reproducibility", "Evaluator isolation", "Enough paired outcomes to estimate intervention advantage"],
    note: "Branching is a research/evaluation mechanism, not a production requirement and not claimed as novel by itself.",
  },
  {
    version: "v0.4.1",
    status: "SHADOW PREDICTION",
    title: "Calibrated intervention value",
    objective: "Learn whether an intervention is worth taking before permitting the model to influence execution.",
    change: [
      "Train an interpretable baseline estimator for action-conditioned downstream utility.",
      "Compare learned predictions with the current heuristic controller on held-out branch outcomes.",
      "Add confidence estimates and an explicit abstain region when action value is uncertain.",
    ],
    gate: ["Calibration on held-out tasks", "Lower intervention regret than current heuristics", "False-pivot rate reported explicitly"],
  },
  {
    version: "v0.4.2",
    status: "OPT-IN ADVISORY",
    title: "Evidence-gated intervention",
    objective: "Expose learned recommendations gradually while retaining the existing controller as the safety fallback.",
    change: [
      "Run the learned value estimator locally at decision points behind a feature flag.",
      "Intervene only above a calibrated advantage threshold; otherwise abstain or use the existing policy.",
      "Persist model version, evidence and prediction alongside the decision snapshot for auditability.",
    ],
    gate: ["No reduction in verified task success", "Measured cost reduction", "Rollback to v0.3 controller at any time"],
  },
  {
    version: "v0.5",
    status: "VNEXT TARGET",
    title: "Project-adaptive execution intelligence",
    objective: "Test the actual novelty hypothesis rather than merely shipping a learned controller.",
    change: [
      "Update intervention priors from longitudinal, verified project experience.",
      "Evaluate transfer across agent harnesses without introducing an LLM controller in the production path.",
      "Treat tokens, tool calls, elapsed time and verification quality as joint execution utility rather than isolated counters.",
    ],
    gate: [
      "Held-out repository evaluation",
      "At least two coding-agent harnesses",
      "Non-inferior success with lower cost or intervention regret",
      "Calibrated abstention under distribution shift",
    ],
  },
];

export function ResearchRoadmap() {
  return (
    <section id="roadmap" aria-labelledby="roadmap-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="roadmap"
          title="vNext research roadmap"
          intro="The transition is deliberately incremental: measure first, learn in shadow mode, validate with matched branches, then expose evidence-gated recommendations. No stage requires replacing the working OpenReflex core before its successor has earned the right to intervene."
        />

        <div className="mt-10 border border-line bg-panel">
          {STAGES.map((stage) => (
            <details key={stage.version} open={stage.version === "v0.3.1"} className="group border-b border-line last:border-b-0">
              <summary className="grid cursor-pointer list-none gap-4 p-5 marker:hidden sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:items-center sm:p-7 [&::-webkit-details-marker]:hidden">
                <span className="font-mono text-sm font-semibold tabular-nums text-accent">{stage.version}</span>
                <div>
                  <h3 className="font-semibold tracking-tight text-ink">{stage.title}</h3>
                  <p className="mt-1 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-muted">{stage.status}</p>
                </div>
                <span className="font-mono text-lg text-muted transition-transform group-open:rotate-45" aria-hidden="true">+</span>
              </summary>

              <div className="border-t border-line bg-bg px-5 py-7 sm:px-7 sm:py-8">
                <p className="max-w-[54rem] font-serif text-[1.28rem] leading-8 text-ink">{stage.objective}</p>
                {stage.note && <p className="mt-5 max-w-[54rem] border-l-2 border-accent pl-4 text-sm leading-6 text-muted">{stage.note}</p>}
                <div className="mt-7 grid gap-8 lg:grid-cols-2">
                  <div>
                    <p className="font-mono text-[0.68rem] uppercase tracking-[0.13em] text-accent">Increment</p>
                    <ul className="mt-4 space-y-3">
                      {stage.change.map((item) => (
                        <li key={item} className="text-sm leading-6 text-text">{item}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="font-mono text-[0.68rem] uppercase tracking-[0.13em] text-accent">Promotion gate</p>
                    <ul className="mt-4 space-y-3">
                      {stage.gate.map((item) => (
                        <li key={item} className="border-t border-line pt-3 text-sm leading-6 text-text first:border-t-0 first:pt-0">{item}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </details>
          ))}
        </div>

        <p className="mt-8 max-w-[64rem] text-sm leading-7 text-muted">
          The public roadmap intentionally omits model architecture, branch-selection heuristics, dataset construction details and
          statistical protocol. Those belong in the experimental report rather than in product documentation.
        </p>
      </div>
    </section>
  );
}
