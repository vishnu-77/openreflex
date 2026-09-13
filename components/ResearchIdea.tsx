import { SectionHeader } from "./SectionHeader";

const IDEAS = [
  {
    title: "It remembers how work went, not what was said",
    body:
      "Most agent memory keeps conversation content and summaries. OpenReflex keeps execution: the path an agent took, " +
      "whether it worked, and the edit that finally resolved an error. That is the part of experience that makes the " +
      "next attempt shorter.",
  },
  {
    title: "It learns without a model",
    body:
      "Every lesson is derived deterministically from lifecycle-hook metadata: tool categories, project-relative paths, " +
      "pass or fail, and masked error lines. Capturing and learning costs no tokens, and nothing is sent to a model or a server.",
  },
  {
    title: "It only trusts verified outcomes",
    body:
      "A task counts as a success only when a test, lint or build passes after the last edit. When nothing verifies the " +
      "result, the outcome stays unknown and no lesson or regret is drawn from it, so guesses never harden into advice.",
  },
  {
    title: "It chooses between approaches",
    body:
      "Before a task, OpenReflex scores candidate strategies (inspect-first, test-first, incremental) on likely success, " +
      "effort, context cost, risk and reversibility. Afterwards it compares the path taken with the best alternative, " +
      "which it calls Execution Regret.",
  },
  {
    title: "One memory for every agent in a project",
    body:
      "Claude Code, Codex, Cursor and OpenCode all write to the same local Experience Graph. A fix learned in one agent's " +
      "session is offered to the next agent that meets the same problem.",
  },
];

export function ResearchIdea() {
  return (
    <section id="idea" aria-labelledby="idea-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="idea"
          title="Execution memory, not conversation memory"
          intro="OpenReflex treats every task an agent runs as evidence about what works in this codebase. It keeps that evidence as a small graph and turns the verified parts into reflexes the next task can use."
        />
        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2 lg:grid-cols-3">
          {IDEAS.map((idea, index) => (
            <div key={idea.title} className="flex flex-col bg-panel p-6 sm:p-8">
              <span className="font-mono text-[0.78rem] tabular-nums text-accent">{index + 1}</span>
              <h3 className="mt-3 text-[1.2rem] font-semibold leading-snug tracking-tight text-ink">{idea.title}</h3>
              <p className="mt-3 leading-[1.7] text-muted">{idea.body}</p>
            </div>
          ))}
          <div className="flex flex-col justify-center bg-panel p-6 sm:p-8">
            <p className="leading-[1.7] text-text">
              See one reflex form, step by step, in the graph explorer below.
            </p>
            <a href="#graph" className="mt-3 text-accent underline-offset-4 hover:underline">
              Open the graph explorer
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
