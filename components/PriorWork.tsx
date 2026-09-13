import { ArrowUpRight } from "lucide-react";
import { RESEARCH_SOURCES } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

type Row = { work: string; kind: string; what: string; how: string; differs: string; sources: (keyof typeof RESEARCH_SOURCES)[] };

// Each description is phrased from the linked source; see RESEARCH_SOURCES.
const ROWS: Row[] = [
  {
    work: "claude-mem",
    kind: "Open-source plugin",
    what: "Captures what a coding agent does in its sessions and injects relevant context into future sessions. Works with Claude Code, Codex, OpenCode and others.",
    how: "Compresses captured sessions with an LLM; stores them locally with vector search, with optional cloud sync.",
    differs: "Learns without a model and never stores session content, only tool metadata, verified outcomes and the fixes that worked.",
    sources: ["claudeMem"],
  },
  {
    work: "Mem0 for Claude Code",
    kind: "Plugin",
    what: "Remembers project knowledge and personal preferences across coding sessions.",
    how: "Hooks save messages, answers, changed files and test results; Mem0's backend extracts and classifies memories.",
    differs: "Keeps everything on your machine and records how tasks went rather than what was said.",
    sources: ["mem0"],
  },
  {
    work: "ReasoningBank",
    kind: "Research, 2025",
    what: "Distils reusable reasoning strategies from an agent's successful and failed experiences; evaluated on web browsing and software engineering benchmarks.",
    how: "The agent judges its own trajectories with an LLM-as-a-judge, then retrieves distilled memories for new tasks.",
    differs: "Judges success by checks that actually passed, and runs as a plugin inside everyday coding agents.",
    sources: ["reasoningBank"],
  },
  {
    work: "Agent Workflow Memory",
    kind: "Research, 2024",
    what: "Induces commonly reused workflows from past experience and provides them to guide later actions; evaluated on web navigation.",
    how: "A language model induces workflows from past trajectories.",
    differs: "Learns per project from live coding-agent hooks, without a model in the loop.",
    sources: ["awm"],
  },
  {
    work: "Agentic Context Engineering",
    kind: "Research, 2025",
    what: "Treats context as an evolving playbook that accumulates and refines strategies.",
    how: "Generation, reflection and curation, adapting from natural execution feedback.",
    differs: "Keeps a structured graph of paths and outcomes and scores alternative strategies, without an LLM curator.",
    sources: ["ace"],
  },
  {
    work: "Reflexion",
    kind: "Research, 2023",
    what: "Agents reflect verbally on task feedback and keep the reflections in an episodic memory buffer for later trials.",
    how: "Self-reflection text written by the model itself.",
    differs: "Lessons persist across sessions and agents in a project, and come from verified outcomes rather than self-reflection.",
    sources: ["reflexion"],
  },
  {
    work: "OpenHands Stuck Detector",
    kind: "Agent framework feature",
    what: "Flags repeating action-observation or action-error cycles, monologues and alternating patterns, and can halt the run.",
    how: "Pattern checks over a single conversation's event history.",
    differs: "Works across four agents through their hooks, and an alert can point to a fix learned in an earlier task.",
    sources: ["openhands"],
  },
];

const SOURCE_ORDER = Object.keys(RESEARCH_SOURCES) as (keyof typeof RESEARCH_SOURCES)[];

function SourceRefs({ keys }: { keys: Row["sources"] }) {
  return (
    <>
      {keys.map((key) => (
        <a key={key} href={`#source-${key}`} className="ml-1 font-mono text-[0.72rem] text-accent align-super">
          [{SOURCE_ORDER.indexOf(key) + 1}]
        </a>
      ))}
    </>
  );
}

export function PriorWork() {
  return (
    <section id="prior-work" aria-labelledby="prior-work-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="prior-work"
          title="Where OpenReflex fits"
          intro="OpenReflex builds on a lot of good work in agent memory and self-improvement. The difference is what it learns from and where that learning happens."
        />

        <div className="hidden overflow-hidden rounded-lg border border-line lg:block">
          <table className="w-full border-collapse text-left">
            <thead className="bg-panel">
              <tr className="text-[0.85rem] text-muted">
                <th scope="col" className="w-[17%] px-5 py-3 font-medium">Work</th>
                <th scope="col" className="w-[29%] px-5 py-3 font-medium">What it does</th>
                <th scope="col" className="w-[24%] px-5 py-3 font-medium">How it learns or detects</th>
                <th scope="col" className="w-[30%] px-5 py-3 font-medium text-accent">How OpenReflex differs</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.work} className="border-t border-line align-top">
                  <th scope="row" className="px-5 py-4 font-normal">
                    <span className="block font-semibold text-ink">
                      {row.work}
                      <SourceRefs keys={row.sources} />
                    </span>
                    <span className="mt-1 block text-[0.85rem] text-muted">{row.kind}</span>
                  </th>
                  <td className="px-5 py-4 leading-relaxed text-text">{row.what}</td>
                  <td className="px-5 py-4 leading-relaxed text-muted">{row.how}</td>
                  <td className="bg-panel/60 px-5 py-4 leading-relaxed text-ink">{row.differs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-4 lg:hidden">
          {ROWS.map((row) => (
            <article key={row.work} className="rounded-lg border border-line bg-panel p-5">
              <h3 className="font-semibold text-ink">
                {row.work}
                <SourceRefs keys={row.sources} />
              </h3>
              <p className="text-[0.85rem] text-muted">{row.kind}</p>
              <p className="mt-3 leading-relaxed text-text">{row.what}</p>
              <p className="mt-2 leading-relaxed text-muted">{row.how}</p>
              <p className="mt-3 border-t border-line pt-3 leading-relaxed text-ink">
                <span className="text-accent">OpenReflex: </span>
                {row.differs}
              </p>
            </article>
          ))}
        </div>

        <div className="mt-10">
          <h3 className="text-sm font-semibold text-ink">Sources</h3>
          <ol className="mt-3 grid gap-x-10 gap-y-2 text-[0.93rem] sm:grid-cols-2">
            {SOURCE_ORDER.map((key, index) => (
              <li key={key} id={`source-${key}`} className="flex gap-2 text-muted">
                <span className="font-mono text-[0.8rem] tabular-nums">{index + 1}.</span>
                <a
                  href={RESEARCH_SOURCES[key].href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-text underline-offset-4 hover:text-accent hover:underline"
                >
                  {RESEARCH_SOURCES[key].label}
                  <ArrowUpRight size={13} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ol>
          <p className="mt-5 max-w-[48rem] text-[0.88rem] leading-relaxed text-muted">
            Descriptions of other projects are summarised from their public documentation and papers as of September 2026.
            Spotted something out of date? Open an issue on GitHub.
          </p>
        </div>
      </div>
    </section>
  );
}
