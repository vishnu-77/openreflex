import { ArrowUpRight } from "lucide-react";
import { NOVELTY_SOURCES } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

type SourceKey = keyof typeof NOVELTY_SOURCES;

const USED_SOURCES: SourceKey[] = [
  "stair",
  "bats",
  "loopArena",
  "harnessRL",
  "calibrationControl",
  "bpo",
  "causalReplay",
  "ecLoop",
  "failureProcess",
];

function Ref({ id }: { id: SourceKey }) {
  return (
    <a href={`#novelty-source-${id}`} className="ml-1 font-mono text-[0.72rem] text-accent align-super">
      [{USED_SOURCES.indexOf(id) + 1}]
    </a>
  );
}

export function NoveltyBoundary() {
  return (
    <section id="novelty" aria-labelledby="novelty-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="novelty"
          title="Novelty and positioning"
          intro="The novelty claim is intentionally narrow. OpenReflex is not presented as a new form of agent memory, budget awareness, runtime control or counterfactual replay; each has substantial prior work. The research target is a specific intervention-learning regime for deployed coding agents."
        />

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="space-y-8">
            <div>
              <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Related work</p>
              <p className="mt-4 max-w-[52rem] leading-7 text-text">
                Historical coding trajectories can already be abstracted into reusable plans through STAIR<Ref id="stair" />.
                Budget-aware agents can adapt planning and pivot under resource constraints through BATS<Ref id="bats" />.
                Runtime controllers for coding agents are directly evaluated by LoopArena<Ref id="loopArena" />, while learned
                harness control has been formalised as an offline-RL problem with a frozen executor<Ref id="harnessRL" />.
                Same-prefix intervention advantage is explicit in Calibration Is Not Control<Ref id="calibrationControl" />;
                BPO branches resumable sandboxes for sibling-return learning<Ref id="bpo" />, and Causal Agent Replay uses
                intervention and re-execution for causal failure attribution<Ref id="causalReplay" />.
              </p>
            </div>

            <div>
              <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Research gap</p>
              <p className="mt-4 max-w-[52rem] leading-7 text-text">
                In the literature reviewed through 16 September 2026, we did not identify a system that combines
                <strong className="font-semibold text-ink"> longitudinal project-specific execution experience</strong>,
                offline matched-branch supervision, cost-sensitive intervention, cross-harness evaluation and a
                privacy-minimised deployment path that requires neither production replay nor an additional LLM controller.
                Early-failure studies and evidence-conditioned execution motivate the need for timely intervention rather than
                establishing this combination themselves<Ref id="failureProcess" /><Ref id="ecLoop" />.
              </p>
            </div>
          </div>

          <aside className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">vNext hypothesis</p>
            <p className="mt-4 font-serif text-[1.35rem] leading-8 text-ink">
              A lightweight controller trained from verified project history and matched execution branches can predict when
              continue, pivot or stop improves realised task utility, while safely abstaining when evidence is insufficient.
            </p>
            <div className="mt-7 border-t border-line pt-6">
              <p className="font-mono text-[0.68rem] uppercase tracking-[0.12em] text-muted">Claim conditions</p>
              <p className="mt-3 text-sm leading-6 text-muted">
                The claim is supported only if held-out experiments show non-inferior task success, lower execution cost or
                intervention regret, calibrated abstention, and transfer across at least two coding-agent harnesses. Until then,
                this remains a falsifiable research hypothesis rather than a product claim.
              </p>
            </div>
          </aside>
        </div>

        <div className="mt-12 border-t border-line pt-8">
          <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-muted">Selected references</p>
          <ol className="mt-4 grid gap-x-10 gap-y-2 text-[0.88rem] sm:grid-cols-2">
            {USED_SOURCES.map((key, index) => (
              <li key={key} id={`novelty-source-${key}`} className="flex gap-2 text-muted">
                <span className="font-mono text-[0.76rem] tabular-nums">{index + 1}.</span>
                <a
                  href={NOVELTY_SOURCES[key].href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-text underline-offset-4 hover:text-accent hover:underline"
                >
                  {NOVELTY_SOURCES[key].label}
                  <ArrowUpRight size={12} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
