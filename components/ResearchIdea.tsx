import { SectionHeader } from "./SectionHeader";

// The closed loop, in the order it runs. Each step describes shipped behaviour in OpenReflex 0.2.
const LOOP = [
  {
    name: "Experience retrieval",
    body:
      "Past tasks live in an Experience Graph: task type, execution path, tool usage, context consumed, verification " +
      "results, failures, outcomes and reusable lessons. A new task retrieves comparable experience from it.",
  },
  {
    name: "Pareto path selection",
    body:
      "Candidate strategies are estimated on expected success, time, tool calls, context cost, uncertainty, risk, " +
      "reversibility and expected regret. A strategy that another beats on every measure is removed as dominated; the " +
      "rest are ranked by utility within the task's limits.",
  },
  {
    name: "Budget-aware execution",
    body:
      "Each task gets a budget for time, context and tool calls. When trouble appears, the current path's success " +
      "estimate is updated with Bayes' rule from calls that made no progress or failed, and the marginal value of more " +
      "work decides whether to continue, pivot to another strategy, or stop.",
  },
  {
    name: "Counterfactual regret",
    body:
      "Afterwards, the realised execution is compared with the best plausible alternative to estimate Execution " +
      "Regret. Regret, cost, outcome and detours feed back into how strategies are ranked for similar tasks.",
  },
];

const CONSTRAINTS = [
  {
    title: "No model in the loop",
    body: "Estimates and lessons are derived deterministically from lifecycle-hook metadata, so learning costs no tokens and nothing leaves the machine.",
  },
  {
    title: "Only verified outcomes count",
    body: "Success means a test, lint or build passed after the last edit. Unverified outcomes produce no lesson and no regret.",
  },
  {
    title: "One graph per project, every agent",
    body: "Claude Code, Codex, Cursor and OpenCode read and write the same local Experience Graph.",
  },
];

export function ResearchIdea() {
  return (
    <section id="idea" aria-labelledby="idea-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="idea"
          title="From memory retrieval to execution optimisation"
          intro="OpenReflex explores budget-aware execution intelligence for AI coding agents. Instead of treating success as a yes or no, it studies how agents choose execution paths, spend tool calls and context, respond to uncertainty, and whether more computation still adds value."
        />

        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2">
          <div className="bg-panel p-6 sm:p-8">
            <p className="text-[0.95rem] text-muted">Most agent memory asks</p>
            <p className="mt-3 font-serif text-[1.5rem] leading-snug text-ink">What past information is relevant?</p>
          </div>
          <div className="bg-panel p-6 sm:p-8">
            <p className="text-[0.95rem] text-muted">OpenReflex also asks</p>
            <p className="mt-3 font-serif text-[1.5rem] leading-snug text-ink">Which execution path should the agent take?</p>
            <p className="mt-2 font-serif text-[1.5rem] leading-snug text-ink">
              Was the chosen path more expensive than a plausible alternative?
            </p>
          </div>
        </div>

        <h3 className="mt-16 text-[1.35rem] font-semibold tracking-tight text-ink">One closed loop</h3>
        <ol className="mt-6 grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2 lg:grid-cols-4">
          {LOOP.map((step, index) => (
            <li key={step.name} className="flex flex-col bg-panel p-6 sm:p-7">
              <span className="font-mono text-[0.78rem] tabular-nums text-accent">{index + 1}</span>
              <h4 className="mt-3 text-[1.12rem] font-semibold leading-snug tracking-tight text-ink">{step.name}</h4>
              <p className="mt-3 leading-[1.7] text-muted">{step.body}</p>
            </li>
          ))}
        </ol>

        <div className="mt-16 grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <div>
            <h3 className="text-[1.35rem] font-semibold tracking-tight text-ink">The research question</h3>
            <p className="mt-4 max-w-[40rem] text-[1.08rem] leading-[1.75] text-text">
              Can repeated execution experience progressively improve the ratio of successful task outcomes to execution
              cost, producing agents that do not merely remember previous work, but learn how to execute future work
              more efficiently?
            </p>
            <blockquote className="mt-8 max-w-[40rem] border-l-2 border-accent pl-5 font-serif text-[1.35rem] leading-snug text-ink">
              Agents should not only remember what worked; they should learn which path produced the best outcome for
              the least execution cost, and adapt future behaviour accordingly.
            </blockquote>
          </div>
          <dl className="grid content-start gap-px overflow-hidden rounded-lg border border-line bg-line">
            {CONSTRAINTS.map((item) => (
              <div key={item.title} className="bg-panel p-6">
                <dt className="font-semibold tracking-tight text-ink">{item.title}</dt>
                <dd className="mt-2 leading-[1.7] text-muted">{item.body}</dd>
              </div>
            ))}
            <div className="bg-panel p-6">
              <a href="#graph" className="text-accent underline-offset-4 hover:underline">
                See one reflex form in the graph explorer
              </a>
            </div>
          </dl>
        </div>
      </div>
    </section>
  );
}
