import { SectionHeader } from "./SectionHeader";

const STEPS = [
  {
    when: "Before a task",
    title: "It hands over what worked",
    body:
      "OpenReflex finds similar past tasks and gives your agent a short briefing: an approach to try, the files that " +
      "were changed last time, and lessons from earlier attempts. If there is nothing relevant yet, it stays silent.",
    sample: [
      "[OpenReflex] debug task, 2 similar past tasks, 2 succeeded",
      "Suggested path: test-first",
      "Likely relevant files: src/auth/session.py",
      "Lesson: token expiry failures were fixed in session.py",
    ],
    tone: "context",
  },
  {
    when: "During a task",
    title: "It steps in when the agent is stuck",
    body:
      "Repeated failing commands, identical retries, stalled progress and runaway context each raise one specific " +
      "alert with a different path to try. It speaks up once, not on every tool call.",
    sample: [
      "OpenReflex: 3 consecutive tool failures.",
      "Stop retrying the same fix: re-read the error",
      "and question the assumption behind it.",
      "Alternative path: inspect-first",
    ],
    tone: "alert",
  },
  {
    when: "After a task",
    title: "It keeps the lesson",
    body:
      "When the task ends, OpenReflex works out whether it succeeded from the checks that actually ran, compares the " +
      "path taken with the alternatives, and saves what it learned for next time.",
    sample: [
      "outcome: success (tests passed after the last edit)",
      "path taken: test-first",
      "lesson: changes landed in src/auth/session.py",
      "lesson: expiry failure resolved by an edit",
    ],
    tone: "lesson",
  },
] as const;

const TONE = {
  context: "border-[#7cc9c8] text-[#9edce0]",
  alert: "border-[#e7b25a] text-[#f1c983]",
  lesson: "border-white/25 text-term-text/85",
};

export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="how"
          title="Every task leaves a trace your agent can use"
          intro="OpenReflex listens to your agent's lifecycle hooks. It never reads your files or transcripts; it learns from what the agent did and how it turned out."
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
      </div>
    </section>
  );
}
