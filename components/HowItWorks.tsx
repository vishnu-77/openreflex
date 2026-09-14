import { SectionHeader } from "./SectionHeader";

// Sample lines are trimmed from real OpenReflex 0.2 engine output.
const STEPS = [
  {
    when: "Before a task",
    title: "It recommends a more efficient path",
    body:
      "OpenReflex finds similar past tasks and compares candidate approaches by expected success, time, tool calls, " +
      "context cost, risk and uncertainty. Your agent gets the best path, a budget, the files that mattered and " +
      "lessons from earlier attempts. If there is nothing relevant yet, it stays silent.",
    sample: [
      "[OpenReflex] debug task | 2 similar past tasks, 2 succeeded",
      "Suggested path: test-first (success~95%, ~14 tool calls)",
      "Alternatives: inspect-first (dominated by test-first)",
      "Budget: ~31 tool calls, ~20 min, ~30k tokens",
      "Likely relevant files: src/auth/session.py",
    ],
    tone: "context",
  },
  {
    when: "During a task",
    title: "It says continue, pivot or stop",
    body:
      "Repeated failures, excessive exploration, context growth and stalled progress are caught as they happen. " +
      "OpenReflex then weighs whether more work on the current path is still worth it, and recommends continuing, " +
      "pivoting to another approach, or stopping to check in with you. It speaks up once, not on every tool call.",
    sample: [
      "OpenReflex: 15 calls over 5 min without a successful edit or check (only read).",
      "Recommendation: pivot to test-first (success estimate ~24% on inspect-first, ~95% for test-first, budget 52% used)",
    ],
    tone: "alert",
  },
  {
    when: "After a task",
    title: "It learns from the outcome",
    body:
      "When the task ends, OpenReflex works out whether it succeeded from the checks that actually ran, compares the " +
      "chosen route with plausible alternatives, and feeds both into the next recommendation.",
    sample: [
      "outcome: success (test passed after the last edit)",
      "path taken: test-first",
      "regret: 0.0 against inspect-first",
      "lesson: \"AssertionError: expired token accepted\" was resolved by an edit in src/auth/session.py",
    ],
    tone: "lesson",
  },
] as const;

const TONE = {
  context: "border-[#7CC9C8] text-[#7CC9C8]",
  alert: "border-[#E7B25A] text-[#E7B25A]",
  lesson: "border-white/25 text-term-text/85",
};

export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="how"
          title="Muscle memory for how work gets done"
          intro="OpenReflex runs alongside Claude Code, Codex, Cursor and OpenCode through plugins, lifecycle hooks and MCP. Install it once and keep working normally. It never reads your files or transcripts; it learns from what the agent did and how it turned out."
        />
        <ol className="grid gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.when} className="flex flex-col bg-panel p-6 sm:p-8">
              <p className="flex items-baseline gap-3 font-mono text-[0.78rem] text-accent">
                <span className="tabular-nums">{index + 1}</span>
                {step.when}
              </p>
              <h3 className="mt-4 text-[1.35rem] font-semibold tracking-tight text-ink">{step.title}</h3>
              <p className="mt-3 flex-1 leading-[1.7] text-muted">{step.body}</p>
              <pre
                className="mt-7 rounded-md bg-term px-4 py-4 font-mono text-[0.74rem] leading-relaxed"
              >
                <code className={`block whitespace-pre-wrap break-words border-l-2 pl-3 ${TONE[step.tone]}`}>{step.sample.join("\n")}</code>
              </pre>
            </li>
          ))}
        </ol>
        <p className="mt-10 max-w-[46rem] text-[1.12rem] leading-[1.7] text-text">
          The goal is simple: help your agents reach the same or better results with fewer unnecessary tool calls, less
          context, less time and less repeated work.
        </p>
      </div>
    </section>
  );
}
