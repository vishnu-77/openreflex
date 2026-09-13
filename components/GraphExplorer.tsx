"use client";

import { useState } from "react";
import { SectionHeader } from "./SectionHeader";

type Step = 1 | 2 | 3 | 4;
type GraphNode = {
  id: string;
  kind: "Task" | "Execution" | "ToolCall" | "Outcome" | "Experience" | "Lesson" | "Context";
  label: string;
  sub: string;
  x: number;
  y: number;
  step: Step;
  alert?: string;
  stored: [string, string][];
  never: string;
};
type Edge = { from: string; to: string; relation: string; step: Step; via?: [number, number] };

const W = 1000;
const H = 560;
const NODE_W = 150;
const NODE_H = 62;

const STEPS: { step: Step; name: string; text: string }[] = [
  {
    step: 1,
    name: "Capture",
    text: "Hooks record the task and each tool call. The same test run fails three times, a loop alert fires, and an edit to dates.py fixes it.",
  },
  { step: 2, name: "Verify", text: "Tests pass after the last edit, so the outcome is recorded as a verified success rather than a guess." },
  { step: 3, name: "Learn", text: "The verified run becomes an experience, and the failing test linked to the edit that fixed it becomes a lesson." },
  {
    step: 4,
    name: "Reuse",
    text: "A similar task starts in a new session, in a different agent. The lesson arrives as an Execution Context before the first tool call.",
  },
];

// A real story from OpenReflex's live Claude Code test suite, drawn with the engine's own node kinds and relations.
const NODES: GraphNode[] = [
  {
    id: "task1", kind: "Task", label: "Task #1041", sub: "Fix parse_date returning the wrong month (Claude Code)", x: 90, y: 90, step: 1,
    stored: [["description", "Fix parse_date returning the wrong month"], ["task_class", "debug"], ["agent", "claude-code"]],
    never: "The rest of the conversation. The prompt is kept only as a short task description, with secrets redacted.",
  },
  {
    id: "exec1", kind: "Execution", label: "Execution", sub: "The first attempt", x: 330, y: 90, step: 1,
    stored: [["recommended path", "test-first"], ["path taken (inferred)", "inspect-first"], ["alerts", "failure_loop"]],
    never: "Transcripts and model output.",
  },
  {
    id: "fail", kind: "ToolCall", label: "Bash · test ×3", sub: "Three identical runs, all failed", x: 570, y: 90, step: 1, alert: "loop alert",
    stored: [["category", "test"], ["status", "failure"], ["fingerprint", "hash of the arguments"], ["error_signature", "AssertionError: (<n>, <n>, <n>) != …"]],
    never: "The command text and its output.",
  },
  {
    id: "fix", kind: "ToolCall", label: "Edit · dates.py", sub: "The change that fixed it", x: 810, y: 90, step: 1,
    stored: [["category", "edit"], ["files", "dates.py"], ["status", "success"]],
    never: "The contents of the edit or of any file.",
  },
  {
    id: "outcome", kind: "Outcome", label: "Outcome", sub: "Verified success", x: 330, y: 290, step: 2,
    stored: [["status", "success"], ["evidence", "test passed after the last edit"], ["verified by", "a real check, not the model"]],
    never: "Unverified guesses. Without a passing check the outcome stays unknown and nothing is learned from it.",
  },
  {
    id: "experience", kind: "Experience", label: "Experience", sub: "What this task taught", x: 570, y: 290, step: 3,
    stored: [["strategy", "inspect-first"], ["status", "success"], ["files", "dates.py, tests/test_dates.py"], ["embedding", "lexical hash of the description"]],
    never: "Code, diffs or file contents.",
  },
  {
    id: "lesson", kind: "Lesson", label: "Lesson", sub: "The reflex", x: 810, y: 290, step: 3,
    stored: [["kind", "resolution"], ["text", "“AssertionError: (<n>, <n>, <n>) != …” was resolved by an edit in dates.py"], ["confidence", "grows as later tasks confirm it"]],
    never: "Anything outside the project folder.",
  },
  {
    id: "task2", kind: "Task", label: "Task #1057", sub: "parse_date is off by one for January dates (Codex)", x: 810, y: 490, step: 4,
    stored: [["description", "parse_date is off by one for January dates"], ["task_class", "debug"], ["agent", "codex"]],
    never: "The rest of the conversation.",
  },
  {
    id: "exec2", kind: "Execution", label: "Execution", sub: "The shorter attempt", x: 570, y: 490, step: 4,
    stored: [["context injected", "yes"], ["outcome", "success, tests passed"], ["failed calls", "none"]],
    never: "Transcripts and model output.",
  },
  {
    id: "context", kind: "Context", label: "Injected context", sub: "The Execution Context the agent was handed", x: 330, y: 490, step: 4,
    stored: [["text", "[OpenReflex] debug task, 1 similar past task, 1 succeeded. Likely relevant files: dates.py …"], ["experience_ids", "the experience above"], ["size", "at most 1,400 characters"]],
    never: "Anything when there is no relevant experience: nothing is injected at all.",
  },
];

const EDGES: Edge[] = [
  { from: "task1", to: "exec1", relation: "caused", step: 1 },
  { from: "exec1", to: "fail", relation: "failed_with", step: 1 },
  { from: "fail", to: "fix", relation: "resolved_by", step: 1 },
  { from: "exec1", to: "outcome", relation: "caused", step: 2 },
  { from: "outcome", to: "experience", relation: "caused", step: 3 },
  { from: "experience", to: "lesson", relation: "caused", step: 3 },
  { from: "lesson", to: "task2", relation: "recommended_for", step: 4 },
  { from: "task2", to: "exec2", relation: "caused", step: 4 },
  { from: "exec2", to: "context", relation: "used", step: 4 },
  { from: "context", to: "experience", relation: "used", step: 4 },
];

const byId = Object.fromEntries(NODES.map((node) => [node.id, node]));

// Point where the segment from (x1,y1) toward (x2,y2) leaves a node's box, so arrows stop at the border.
function exitPoint(x1: number, y1: number, x2: number, y2: number, gap = 6): [number, number] {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const tx = dx === 0 ? Infinity : (NODE_W / 2 + gap) / Math.abs(dx);
  const ty = dy === 0 ? Infinity : (NODE_H / 2 + gap) / Math.abs(dy);
  const t = Math.min(tx, ty);
  return [x1 + dx * t, y1 + dy * t];
}

function edgePath(edge: Edge) {
  const a = byId[edge.from];
  const b = byId[edge.to];
  const [cx, cy] = edge.via ?? [b.x, b.y];
  const [sx, sy] = exitPoint(a.x, a.y, cx, cy);
  const [ex, ey] = edge.via ? exitPoint(b.x, b.y, cx, cy) : exitPoint(b.x, b.y, a.x, a.y);
  const d = edge.via ? `M${sx} ${sy} L${cx} ${cy} L${ex} ${ey}` : `M${sx} ${sy} L${ex} ${ey}`;
  // Horizontal edges get their label above the node row, so long relation names never collide with boxes.
  const horizontal = !edge.via && Math.abs(a.y - b.y) < 1;
  const label: [number, number] = edge.via
    ? [cx, (sy + cy) / 2]
    : horizontal
      ? [(sx + ex) / 2, a.y - NODE_H / 2 - 4]
      : [(sx + ex) / 2, (sy + ey) / 2 + 5];
  return { d, label };
}

export function GraphExplorer() {
  const [step, setStep] = useState<Step>(1);
  const [selected, setSelected] = useState("task1");
  const node = byId[selected];

  function pickStep(next: Step) {
    setStep(next);
    setSelected(NODES.find((item) => item.step === next)!.id);
  }

  function pickNode(id: string) {
    setSelected(id);
    setStep(byId[id].step);
  }

  const tone = (itemStep: Step) => (itemStep === step ? "current" : itemStep < step ? "past" : "future");
  const current = STEPS[step - 1];

  return (
    <section id="graph" aria-labelledby="graph-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="graph"
          title="Watch one reflex form"
          intro="This is the Experience Graph for a real bug fix, using the same node types and relations the engine stores. Step through it, or select any node to see exactly what OpenReflex keeps."
        />

        <div role="tablist" aria-label="Stages" className="grid grid-cols-2 overflow-hidden rounded-lg border border-line sm:grid-cols-4">
          {STEPS.map((item) => {
            const active = item.step === step;
            return (
              <button
                key={item.step}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => pickStep(item.step)}
                className={`flex items-baseline gap-3 border-line px-5 py-4 text-left transition-colors [&:not(:first-child)]:border-l ${
                  active ? "bg-panel text-ink" : "text-muted hover:bg-panel/60 hover:text-ink"
                }`}
              >
                <span className={`font-mono text-[0.8rem] tabular-nums ${active ? "text-accent" : ""}`}>{item.step}</span>
                <span className="font-medium">{item.name}</span>
              </button>
            );
          })}
        </div>
        <p className="mt-4 max-w-[52rem] leading-relaxed text-text" aria-live="polite">
          {current.text}
        </p>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="relative hidden w-full md:block" style={{ aspectRatio: `${W} / ${H}` }}>
            <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full" aria-hidden="true">
              <defs>
                <marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0 0L10 5L0 10z" className="fill-accent" />
                </marker>
                <marker id="arrow-off" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0 0L10 5L0 10z" className="fill-line-strong" />
                </marker>
              </defs>
              {EDGES.map((edge) => {
                const { d, label } = edgePath(edge);
                const state = tone(edge.step);
                const on = state === "current";
                return (
                  <g key={`${edge.from}-${edge.to}`} className={state === "future" ? "opacity-25" : ""}>
                    <path
                      d={d}
                      fill="none"
                      className={on ? "stroke-accent" : "stroke-line-strong"}
                      strokeWidth={on ? 2.2 : 1.4}
                      markerEnd={`url(#${on ? "arrow-on" : "arrow-off"})`}
                    />
                    <text
                      x={label[0]}
                      y={label[1] - 7}
                      textAnchor="middle"
                      className={`font-mono ${on ? "fill-accent" : "fill-muted"}`}
                      style={{ fontSize: 13, paintOrder: "stroke", stroke: "var(--bg)", strokeWidth: 6 }}
                    >
                      {edge.relation}
                    </text>
                  </g>
                );
              })}
            </svg>
            {NODES.map((item) => {
              const state = tone(item.step);
              const isSelected = item.id === selected;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => pickNode(item.id)}
                  aria-pressed={isSelected}
                  aria-label={`${item.kind}: ${item.label}. ${item.sub}`}
                  className={`absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-start justify-center rounded-md border px-3 text-left transition-colors ${
                    isSelected
                      ? "border-accent bg-panel ring-1 ring-accent"
                      : state === "current"
                        ? "border-accent bg-panel"
                        : "border-line bg-panel hover:border-line-strong"
                  } ${state === "future" ? "opacity-40" : ""}`}
                  style={{
                    left: `${(item.x / W) * 100}%`,
                    top: `${(item.y / H) * 100}%`,
                    width: `${(NODE_W / W) * 100}%`,
                    height: `${(NODE_H / H) * 100}%`,
                  }}
                >
                  <span className="font-mono text-[0.68rem] text-muted">{item.kind}</span>
                  <span className="w-full truncate text-[0.85rem] font-medium leading-tight text-ink">{item.label}</span>
                  {item.alert && (
                    <span className="absolute -top-2.5 right-2 rounded-sm bg-[#E7B25A] px-1.5 font-mono text-[0.62rem] leading-[1.35rem] text-[#171511]">
                      {item.alert}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="grid gap-2 md:hidden">
            {NODES.filter((item) => item.step === step).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => pickNode(item.id)}
                aria-pressed={item.id === selected}
                className={`flex items-center justify-between gap-3 rounded-md border px-4 py-3 text-left ${
                  item.id === selected ? "border-accent bg-panel" : "border-line bg-panel"
                }`}
              >
                <span className="flex flex-col">
                  <span className="font-mono text-[0.7rem] text-muted">{item.kind}</span>
                  <span className="font-medium text-ink">{item.label}</span>
                </span>
                {item.alert && <span className="rounded-sm bg-[#E7B25A] px-1.5 font-mono text-[0.65rem] text-[#171511]">{item.alert}</span>}
              </button>
            ))}
          </div>

          <aside className="flex flex-col gap-4 rounded-lg border border-line bg-panel p-5" aria-live="polite">
            <div className="flex flex-col gap-1">
              <span className="font-mono text-[0.75rem] text-accent">{node.kind}</span>
              <h3 className="text-lg font-semibold leading-snug text-ink">{node.label}</h3>
              <p className="text-muted">{node.sub}</p>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-ink">Stored</h4>
              <dl className="mt-2">
                {node.stored.map(([key, value]) => (
                  <div key={key} className="flex flex-col gap-0.5 border-t border-line py-2">
                    <dt className="font-mono text-[0.72rem] text-muted">{key}</dt>
                    <dd className="break-words text-[0.9rem] text-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="border-t border-line pt-3">
              <h4 className="text-sm font-semibold text-ink">Never stored</h4>
              <p className="mt-1 text-[0.9rem] leading-relaxed text-muted">{node.never}</p>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
