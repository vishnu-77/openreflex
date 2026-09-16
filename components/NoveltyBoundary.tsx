import { ArrowUpRight } from "lucide-react";
import { NOVELTY_SOURCES } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

type SourceKey = keyof typeof NOVELTY_SOURCES;

type PriorArt = {
  work: string;
  territory: string;
  implication: string;
  sources: SourceKey[];
};

const SOURCE_ORDER = Object.keys(NOVELTY_SOURCES) as SourceKey[];

const CLOSEST_WORK: PriorArt[] = [
  {
    work: "Calibration Is Not Control",
    territory:
      "Same-prefix counterfactual branching and action-conditioned intervention advantage: compare continue, intervene and quit from matched trajectory states.",
    implication:
      "Prefix branching and intervention advantage are direct prior art. OpenReflex must treat them as baselines, not novelty claims.",
    sources: ["calibrationControl"],
  },
  {
    work: "Branching Policy Optimization",
    territory:
      "Snapshots intermediate sandbox states, forks alternative actions and rolls sibling branches to termination; evaluated on SWE-bench Verified as a training signal.",
    implication:
      "Branchable coding environments and sibling-return comparisons already exist. The open question is deployment-time control for existing agents rather than policy training itself.",
    sources: ["bpo"],
  },
  {
    work: "LoopArena",
    territory:
      "Benchmarks a separate runtime Controller that reads structured evidence, directs a fixed coding Worker, requests verification and decides when to stop.",
    implication:
      "A controller around a coding agent is occupied territory. OpenReflex needs a different learning substrate and deployment constraint, not merely a controller role.",
    sources: ["loopArena"],
  },
  {
    work: "Learning to Control LLM Agent Harnesses",
    territory:
      "Formalises the harness as a finite-horizon MDP and trains a lightweight controller from offline rollouts while the LLM executor remains frozen.",
    implication:
      "Learned harness control is also prior art. A vNext contribution must be more specific than 'learn the outer loop'.",
    sources: ["harnessRL"],
  },
  {
    work: "BATS / budget-aware test-time scaling",
    territory:
      "Tracks remaining resources and adapts planning and verification, including whether to keep digging or pivot to a new path.",
    implication:
      "Budget awareness, tool-call economics and pivoting are not independently novel.",
    sources: ["bats"],
  },
  {
    work: "STAIR / trajectory reuse for coding agents",
    territory:
      "Turns previous repair trajectories into hierarchical reusable plans and transfers those plans across coding agents.",
    implication:
      "Historical coding trajectories as reusable procedural knowledge are prior art; OpenReflex should not lead with 'memory of what worked'.",
    sources: ["stair"],
  },
  {
    work: "Causal Agent Replay",
    territory:
      "Intervenes on recorded agent steps and re-runs downstream execution to estimate causal effects and locate failure-causing decisions.",
    implication:
      "Counterfactual replay itself is occupied. OpenReflex should use replay to supervise future intervention decisions rather than claim replay as the contribution.",
    sources: ["causalReplay"],
  },
  {
    work: "ECLoop + Failure as a Process",
    territory:
      "Shows that coding-agent failures often begin before they become visible, and that an external execution layer can redirect poorly evidenced actions before commitment.",
    implication:
      "Early runtime intervention in coding agents is established motivation and a required baseline, not a novelty claim.",
    sources: ["ecLoop", "failureProcess"],
  },
];

function Refs({ keys }: { keys: SourceKey[] }) {
  return (
    <>
      {keys.map((key) => (
        <a key={key} href={`#novelty-source-${key}`} className="ml-1 font-mono text-[0.72rem] text-accent align-super">
          [{SOURCE_ORDER.indexOf(key) + 1}]
        </a>
      ))}
    </>
  );
}

export function NoveltyBoundary() {
  return (
    <section id="novelty" aria-labelledby="novelty-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="novelty"
          title="Novelty boundary"
          intro="The research claim is deliberately narrower than the product. OpenReflex does not claim that agent memory, budget awareness, runtime control, branching, stopping or trajectory reuse are new. The question is whether a particular deployment regime can turn verified local experience into better intervention decisions without placing another LLM in the control path."
        />

        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-3">
          <div className="bg-panel p-6 sm:p-7">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-muted">Established / occupied</p>
            <p className="mt-4 leading-7 text-text">
              Trajectory memory, reusable skills, budget-aware tool use, learned harness controllers, prefix branching,
              intervention advantage, counterfactual replay and runtime coding-agent controllers all have direct prior work.
            </p>
          </div>
          <div className="bg-panel p-6 sm:p-7">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-muted">Recombination</p>
            <p className="mt-4 leading-7 text-text">
              OpenReflex already combines local lifecycle telemetry, verified outcomes, cross-session experience, cost-aware
              routing and continue / pivot / stop decisions across existing coding-agent harnesses. The combination is useful,
              but combination alone is not treated as a research result.
            </p>
          </div>
          <div className="bg-bg-soft p-6 sm:p-7">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">vNext research target</p>
            <p className="mt-4 leading-7 text-ink">
              Learn a project-adaptive, cost-sensitive intervention policy from verified coding executions and offline matched
              branches, then deploy it locally from privacy-minimised telemetry with no production replay and no additional LLM
              controller. The policy must know when evidence is insufficient and abstain from intervention.
            </p>
          </div>
        </div>

        <div className="mt-14 overflow-hidden rounded-lg border border-line">
          <div className="hidden lg:block">
            <table className="w-full border-collapse text-left">
              <thead className="bg-panel text-[0.84rem] text-muted">
                <tr>
                  <th className="w-[22%] px-5 py-3 font-medium">Closest work</th>
                  <th className="w-[40%] px-5 py-3 font-medium">What it already occupies</th>
                  <th className="w-[38%] px-5 py-3 font-medium text-accent">Consequence for OpenReflex</th>
                </tr>
              </thead>
              <tbody>
                {CLOSEST_WORK.map((row) => (
                  <tr key={row.work} className="border-t border-line align-top">
                    <th className="px-5 py-4 font-semibold text-ink">
                      {row.work}
                      <Refs keys={row.sources} />
                    </th>
                    <td className="px-5 py-4 leading-7 text-muted">{row.territory}</td>
                    <td className="bg-panel/60 px-5 py-4 leading-7 text-text">{row.implication}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-px bg-line lg:hidden">
            {CLOSEST_WORK.map((row) => (
              <article key={row.work} className="bg-panel p-5">
                <h3 className="font-semibold text-ink">
                  {row.work}
                  <Refs keys={row.sources} />
                </h3>
                <p className="mt-3 leading-7 text-muted">{row.territory}</p>
                <p className="mt-4 border-t border-line pt-4 leading-7 text-text">{row.implication}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-14 grid gap-6 lg:grid-cols-2">
          <div className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Falsifiable novelty hypothesis</p>
            <p className="mt-4 font-serif text-[1.35rem] leading-8 text-ink">
              Can a lightweight controller, trained from matched coding-agent branches plus longitudinal project experience,
              predict when a specific intervention will improve realised task utility and transfer that policy across agent
              harnesses using only privacy-minimised execution telemetry?
            </p>
          </div>
          <div className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">What would defend the claim</p>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-text">
              <li>Matched-prefix branch data with realised downstream utility, not guessed counterfactuals.</li>
              <li>Equal-success or non-inferior task quality with statistically significant reductions in tokens, tool calls, time or cost.</li>
              <li>Lower intervention regret than static budgets, current OpenReflex heuristics, BATS-style control and action-conditioned controller baselines.</li>
              <li>Calibrated abstention: false pivots and unnecessary interventions must fall as confidence thresholds tighten.</li>
              <li>Held-out repositories and at least two agent harnesses to test whether the policy learns execution structure rather than one agent's quirks.</li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-l-2 border-accent pl-5">
          <p className="max-w-[62rem] text-sm leading-7 text-muted">
            Status as of September 2026: this is a research target, not a claimed result. A literature search found no work in
            the set reviewed here that simultaneously demonstrates project-longitudinal adaptation, matched-branch supervision,
            cost-sensitive coding intervention, cross-harness transfer, privacy-minimised telemetry and zero-LLM / zero-replay
            deployment. Any future novelty claim should be limited to the combination actually demonstrated by experiments.
          </p>
        </div>

        <div className="mt-12">
          <h3 className="text-sm font-semibold text-ink">Closest-work sources</h3>
          <ol className="mt-3 grid gap-x-10 gap-y-2 text-[0.93rem] sm:grid-cols-2">
            {SOURCE_ORDER.map((key, index) => (
              <li key={key} id={`novelty-source-${key}`} className="flex gap-2 text-muted">
                <span className="font-mono text-[0.8rem] tabular-nums">{index + 1}.</span>
                <a
                  href={NOVELTY_SOURCES[key].href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-text underline-offset-4 hover:text-accent hover:underline"
                >
                  {NOVELTY_SOURCES[key].label}
                  <ArrowUpRight size={13} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
