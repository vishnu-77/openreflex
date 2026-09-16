import { ArrowUpRight } from "lucide-react";
import { SectionHeader } from "./SectionHeader";

type ReleaseNote = {
  version: string;
  title: string;
  observation: string;
  evidence: string[];
  href: string;
};

const RELEASES: ReleaseNote[] = [
  {
    version: "v0.3.2",
    title: "Observation integrity",
    observation:
      "The released instrumentation was hardened so malformed or context-poor activity does not contaminate the explanation surface.",
    evidence: [
      "Malformed hook events without a tool identity are ignored.",
      "Explanation commands resolve to the latest task that actually contains decision evidence.",
      "The live Codex harness reports agent refusal causes more accurately.",
    ],
    href: "https://github.com/vishnu-77/openreflex/releases/tag/v0.3.2",
  },
  {
    version: "v0.3.1",
    title: "Evidence semantics and user control",
    observation:
      "The public interface was tightened so research-facing concepts have explicit meanings and stored experience remains user-removable.",
    evidence: [
      "MCP tool contracts define return values, intended use and side effects more precisely.",
      "Execution Regret and Reflex Score are defined where they appear.",
      "Individual stored experiences can be explicitly forgotten.",
    ],
    href: "https://github.com/vishnu-77/openreflex/releases/tag/v0.3.1",
  },
  {
    version: "v0.3.0",
    title: "Observable execution policy",
    observation:
      "Execution recommendations became inspectable rather than opaque, separating recommendation strength from estimated task success.",
    evidence: [
      "Decision snapshots persist route, confidence, evidence, budget pressure and context overhead.",
      "Reflex Score exposes recommendation strength independently of success probability.",
      "`why` and `trace` read the same stored decision evidence used by the runtime.",
    ],
    href: "https://github.com/vishnu-77/openreflex/releases/tag/v0.3.0",
  },
  {
    version: "v0.2.0",
    title: "Budget-aware execution",
    observation:
      "OpenReflex moved from retrieval alone toward execution optimisation by treating agent work as a constrained multi-objective process.",
    evidence: [
      "Candidate paths are compared across success, time, tool calls, context, risk, uncertainty and reversibility.",
      "Tasks receive execution budgets for tool calls, active time and context.",
      "Runtime advice can recommend continue, pivot or stop when progress deteriorates.",
    ],
    href: "https://github.com/vishnu-77/openreflex/releases/tag/v0.2.0",
  },
];

export function ResearchRoadmap() {
  return (
    <section id="roadmap" aria-labelledby="roadmap-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="roadmap"
          title="Research notes by release"
          intro="This section is retrospective by design. It records the research-relevant behaviour that is already public, shipped and inspectable. New entries are added only when a release makes the corresponding evidence available."
        />

        <div className="mt-10 border border-line bg-panel">
          {RELEASES.map((release) => (
            <article key={release.version} className="border-b border-line p-5 last:border-b-0 sm:p-7">
              <div className="grid gap-4 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:items-start">
                <span className="font-mono text-sm font-semibold tabular-nums text-accent">{release.version}</span>
                <div>
                  <h3 className="font-semibold tracking-tight text-ink">{release.title}</h3>
                  <p className="mt-3 max-w-[54rem] leading-7 text-text">{release.observation}</p>
                  <ul className="mt-5 space-y-2">
                    {release.evidence.map((item) => (
                      <li key={item} className="text-sm leading-6 text-muted">{item}</li>
                    ))}
                  </ul>
                </div>
                <a
                  href={release.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 font-mono text-[0.72rem] uppercase tracking-[0.1em] text-muted underline-offset-4 hover:text-accent hover:underline"
                >
                  Release
                  <ArrowUpRight size={12} aria-hidden="true" />
                </a>
              </div>
            </article>
          ))}
        </div>

        <p className="mt-8 max-w-[64rem] text-sm leading-7 text-muted">
          This is not a forward roadmap. Ongoing research, unreleased implementation details and future experiments remain private
          until they are ready to be introduced with a public release and supporting evidence.
        </p>
      </div>
    </section>
  );
}
