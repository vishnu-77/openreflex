import { ArrowUpRight } from "lucide-react";
import { NOVELTY_SOURCES } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

type SourceKey = keyof typeof NOVELTY_SOURCES;

const USED_SOURCES: SourceKey[] = ["stair", "bats", "loopArena", "harnessRL", "ecLoop"];

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
          intro="OpenReflex does not claim novelty for agent memory, budget awareness or runtime control in isolation. The public research position is restricted to the combination and evidence already present in released versions."
        />

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="space-y-8">
            <div>
              <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Related work</p>
              <p className="mt-4 max-w-[52rem] leading-7 text-text">
                Historical coding trajectories can already be abstracted into reusable plans through STAIR<Ref id="stair" />.
                Budget-aware agents can adapt planning under resource constraints through BATS<Ref id="bats" />.
                Runtime controllers for coding agents are evaluated by LoopArena<Ref id="loopArena" />, while learned harness
                control has also been formalised with a frozen executor<Ref id="harnessRL" />. Evidence-conditioned execution
                systems such as ECLoop further show that runtime intervention is an active research area<Ref id="ecLoop" />.
              </p>
            </div>

            <div>
              <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Released position</p>
              <p className="mt-4 max-w-[52rem] leading-7 text-text">
                OpenReflex currently combines project-local execution experience, multi-objective path selection, execution
                budgets, runtime continue / pivot / stop recommendations, and observable decision evidence. These are treated as
                an experimental system design rather than as individually novel primitives.
              </p>
            </div>
          </div>

          <aside className="border border-line bg-panel p-6 sm:p-8">
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-accent">Publication policy</p>
            <p className="mt-4 font-serif text-[1.35rem] leading-8 text-ink">
              Research claims are added here only after the corresponding capability has shipped and can be inspected or measured.
            </p>
            <div className="mt-7 border-t border-line pt-6">
              <p className="font-mono text-[0.68rem] uppercase tracking-[0.12em] text-muted">What is intentionally absent</p>
              <p className="mt-3 text-sm leading-6 text-muted">
                Unreleased hypotheses, internal experiments, future evaluation protocols and implementation directions are not
                published on this page. They will be introduced progressively with releases and supporting evidence.
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
