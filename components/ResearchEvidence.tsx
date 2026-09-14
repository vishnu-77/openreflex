import { ArrowUpRight } from "lucide-react";
import { EVIDENCE_SOURCES } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

type Finding = {
  title: string;
  quote: string;
  detail?: string;
  source: keyof typeof EVIDENCE_SOURCES;
  where: string;
  uses: string;
};

// Every quote is verbatim from the linked paper (checked against arXiv on 15 September 2026).
const FINDINGS: Finding[] = [
  {
    title: "Failed runs are longer, not just wrong",
    quote:
      "…we find that failed trajectories are consistently longer and exhibit higher variance than successful ones, with failure patterns differing significantly between agents.",
    detail:
      "In the paper's own measurements (Section 4.2), failed trajectories took between 12.6% and 82.5% more steps than successful ones, depending on the agent (OpenHands, SWE-agent or Prometheus) and the SWE-Bench split.",
    source: "trajectories",
    where: "Abstract",
    uses:
      "OpenReflex watches the shape of a run while it happens: identical calls repeated, failures in a row, long stretches without a successful edit or check, and work past the task's budget. When none of those appear, it stays silent.",
  },
  {
    title: "Agents stall in their own reasoning",
    quote: "…with the majority of agentic failures stemming from flawed reasoning and cognitive deadlocks.",
    detail:
      "The authors respond with a second, supervisory agent that provides strategic oversight and course-correction for the agent doing the work.",
    source: "failures",
    where: "Abstract",
    uses:
      "OpenReflex also corrects course from outside the agent, but without a second model. Its recommendation to continue, pivot or stop is computed from lifecycle-hook signals and verified outcomes, and it is advice the agent can weigh, never a block on its tools.",
  },
  {
    title: "Language feedback can change behaviour without retraining",
    quote:
      "We propose Reflexion, a novel framework to reinforce language agents not by updating weights, but instead through linguistic feedback.",
    source: "reflexion",
    where: "Abstract",
    uses:
      "OpenReflex likewise works through text placed in the agent's context rather than through training. It differs in where that text comes from: Reflexion agents write their own reflections and reuse them on later trials, while OpenReflex derives its context deterministically from hook metadata and checks that actually passed, and keeps it across sessions and across agents.",
  },
];

export function ResearchEvidence() {
  return (
    <section id="evidence" aria-labelledby="evidence-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="evidence"
          title="What the research says"
          intro="Three published studies shaped how OpenReflex works. Each is quoted from the paper itself, next to what OpenReflex takes from it and where it goes its own way."
        />

        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line">
          {FINDINGS.map((finding) => {
            const source = EVIDENCE_SOURCES[finding.source];
            return (
              <article key={finding.source} className="grid bg-panel lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
                <div className="p-6 sm:p-8">
                  <h3 className="text-[1.2rem] font-semibold leading-snug tracking-tight text-ink">{finding.title}</h3>
                  <blockquote className="mt-5 border-l-2 border-accent pl-5 font-serif text-[1.22rem] leading-[1.5] text-ink">
                    <p>“{finding.quote}”</p>
                  </blockquote>
                  <p className="mt-4 text-[0.92rem] leading-relaxed text-muted">
                    {source.authors} ({source.year}).{" "}
                    <a
                      href={source.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-text underline underline-offset-4 hover:text-accent"
                    >
                      <cite className="not-italic">{source.title}</cite>
                      <ArrowUpRight size={13} aria-hidden="true" className="ml-0.5 inline align-baseline" />
                    </a>{" "}
                    {source.id}, {finding.where.toLowerCase()}.
                  </p>
                  {finding.detail && <p className="mt-4 max-w-[40rem] leading-[1.7] text-text">{finding.detail}</p>}
                </div>
                <div className="border-t border-line p-6 sm:p-8 lg:border-l lg:border-t-0">
                  <p className="text-[0.9rem] font-medium text-accent">What OpenReflex takes from it</p>
                  <p className="mt-3 leading-[1.7] text-text">{finding.uses}</p>
                </div>
              </article>
            );
          })}
        </div>

        <p className="mt-8 max-w-[52rem] text-[0.92rem] leading-relaxed text-muted">
          OpenReflex is an independent open-source project. It is not affiliated with the authors of these papers, uses
          none of their code, and is not an implementation of Reflexion; its name comes from reflexes, the learned
          responses it builds up for a project. Numbers quoted here describe the papers&apos; own experiments, not
          OpenReflex.
        </p>
      </div>
    </section>
  );
}
