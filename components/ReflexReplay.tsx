"use client";

import { RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Kind = "cmd" | "tool" | "fail" | "ok" | "alert" | "context" | "recap" | "lesson" | "divider" | "meta";
type Line = { kind: Kind; text: string; detail?: string; pause?: number };
type AgentDemo = { id: string; name: string; surface: string; script: Line[] };

const SHARED_END: Line[] = [
  { kind: "fail", text: "Bash   python -m pytest tests/test_auth.py -q", detail: "1 failed" },
  { kind: "tool", text: "Edit   src/auth/session.py" },
  { kind: "ok", text: "Bash   python -m pytest tests/test_auth.py -q", detail: "8 passed", pause: 500 },
];

const AGENTS: AgentDemo[] = [
  {
    id: "claude",
    name: "Claude Code",
    surface: "visible recap + hidden additionalContext",
    script: [
      { kind: "cmd", text: 'claude "fix expired authentication tokens still being accepted"', pause: 650 },
      { kind: "recap", text: "↺ OpenReflex · 82", detail: "2 experiences · test-first 95% · ~14 calls · +184 context tokens", pause: 900 },
      { kind: "context", text: "agent context → likely file src/auth/session.py · test-first recommended" },
      { kind: "tool", text: "Read   src/auth/session.py" },
      { kind: "tool", text: "Read   src/auth/validator.py" },
      { kind: "tool", text: "Read   tests/test_auth.py" },
      { kind: "meta", text: "… exploration continues without a successful edit or check …", pause: 500 },
      { kind: "alert", text: "↺ OpenReflex · 64 ↓18", detail: "15 calls · budget 52% · pivot → test-first", pause: 1000 },
      ...SHARED_END,
      { kind: "recap", text: "↺ OpenReflex · COMPLETE", detail: "success · test-first · 18 calls · regret 0.00 vs inspect-first", pause: 900 },
      { kind: "lesson", text: 'learned → "expired token accepted" was resolved by an edit in src/auth/session.py', pause: 900 },
    ],
  },
  {
    id: "codex",
    name: "Codex",
    surface: "hook/MCP context; no Claude-style visible recap",
    script: [
      { kind: "cmd", text: 'codex "fix expired authentication tokens still being accepted"', pause: 650 },
      { kind: "context", text: "additionalContext → 2 experiences · test-first 95% · likely src/auth/session.py", pause: 850 },
      { kind: "tool", text: "Read   src/auth/session.py" },
      { kind: "tool", text: "Read   src/auth/validator.py" },
      { kind: "meta", text: "… current path keeps exploring …" },
      { kind: "context", text: "additionalContext → progress stalled · pivot to test-first · budget 52%", pause: 950 },
      ...SHARED_END,
      { kind: "lesson", text: "OpenReflex stored outcome, chosen path, regret and resolution lesson", pause: 850 },
    ],
  },
  {
    id: "cursor",
    name: "Cursor",
    surface: "context delivered after the first tool result",
    script: [
      { kind: "cmd", text: "Cursor task → fix expired authentication tokens still being accepted", pause: 650 },
      { kind: "tool", text: "Read   src/auth/session.py", pause: 450 },
      { kind: "context", text: "additional_context → 2 experiences · test-first 95% · likely src/auth/session.py", pause: 850 },
      { kind: "tool", text: "Read   src/auth/validator.py" },
      { kind: "meta", text: "… execution evidence accumulates …" },
      { kind: "context", text: "additional_context → progress stalled · test-first now preferred", pause: 950 },
      ...SHARED_END,
      { kind: "lesson", text: "OpenReflex stored outcome, path, regret and reusable resolution", pause: 850 },
    ],
  },
  {
    id: "opencode",
    name: "OpenCode",
    surface: "plugin event context + MCP",
    script: [
      { kind: "cmd", text: 'opencode → "fix expired authentication tokens still being accepted"', pause: 650 },
      { kind: "context", text: "plugin context → 2 experiences · test-first 95% · likely src/auth/session.py", pause: 850 },
      { kind: "tool", text: "Read   src/auth/session.py" },
      { kind: "tool", text: "Read   src/auth/validator.py" },
      { kind: "meta", text: "… execution evidence accumulates …" },
      { kind: "context", text: "plugin context → pivot recommendation: test-first · budget 52%", pause: 950 },
      ...SHARED_END,
      { kind: "lesson", text: "OpenReflex stored outcome, path, regret and reusable resolution", pause: 850 },
    ],
  },
];

function Row({ line }: { line: Line }) {
  switch (line.kind) {
    case "cmd":
      return (
        <p className="text-term-text">
          <span className="select-none text-term-dim">$ </span>
          {line.text}
        </p>
      );
    case "divider":
      return (
        <p className="my-3 flex items-center gap-3 text-term-dim" role="separator">
          <span className="h-px flex-1 bg-white/10" />
          {line.text}
          <span className="h-px flex-1 bg-white/10" />
        </p>
      );
    case "alert":
      return (
        <div className="my-1.5 border-l-2 border-[#E7B25A] bg-[#E7B25A]/10 py-1.5 pl-3 pr-2 text-[#E7B25A]">
          <p>{line.text}</p>
          {line.detail && <p className="mt-0.5 text-[0.92em] opacity-85">{line.detail}</p>}
        </div>
      );
    case "recap":
      return (
        <div className="my-1.5 border-l-2 border-[#7CC9C8] bg-[#7CC9C8]/[0.07] py-1.5 pl-3 pr-2 text-[#7CC9C8]">
          <p>{line.text}</p>
          {line.detail && <p className="mt-0.5 text-[0.92em] opacity-85">{line.detail}</p>}
        </div>
      );
    case "context":
      return <p className="border-l-2 border-[#7CC9C8]/70 pl-3 text-[#7CC9C8]">{line.text}</p>;
    case "lesson":
      return <p className="pl-3 text-[#7CC9C8]/80">{line.text}</p>;
    case "meta":
      return <p className="py-1 pl-3 italic text-term-dim">{line.text}</p>;
    default: {
      const tone = line.kind === "fail" ? "text-term-text" : line.kind === "ok" ? "text-[#7CC9C8]" : "";
      const mark = line.kind === "fail" ? "x" : line.kind === "ok" ? "ok" : "";
      return (
        <p className="flex justify-between gap-4 pl-3 text-term-text/85">
          <span className="whitespace-pre">{line.text}</span>
          {line.detail && (
            <span className={`shrink-0 ${tone}`}>
              {mark} {line.detail}
            </span>
          )}
        </p>
      );
    }
  }
}

export function ReflexReplay() {
  const [active, setActive] = useState(AGENTS[0].id);
  const agent = useMemo(() => AGENTS.find((item) => item.id === active) ?? AGENTS[0], [active]);
  const [reduceMotion, setReduceMotion] = useState<boolean | null>(null);
  const [shown, setShown] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReduceMotion(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const play = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setShown(0);
    let index = 0;
    const step = () => {
      index += 1;
      setShown(index);
      if (index < agent.script.length) timer.current = setTimeout(step, agent.script[index - 1].pause ?? 420);
    };
    timer.current = setTimeout(step, 450);
  }, [agent]);

  useEffect(() => {
    if (reduceMotion === null) return;
    if (reduceMotion) {
      setShown(agent.script.length);
      return;
    }
    play();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [agent, play, reduceMotion]);

  const done = shown >= agent.script.length;

  return (
    <figure className="overflow-hidden rounded-lg border border-line-strong/60 bg-term shadow-[0_24px_60px_-28px_rgba(0,0,0,0.55)]">
      <div className="border-b border-white/10">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          </div>
          <figcaption className="font-mono text-[0.72rem] text-term-dim">OpenReflex execution replay</figcaption>
          <button
            type="button"
            onClick={play}
            disabled={!done}
            className="flex items-center gap-1.5 font-mono text-[0.72rem] text-term-dim transition-colors enabled:hover:text-term-text disabled:opacity-0"
          >
            <RotateCcw size={12} aria-hidden="true" />
            Replay
          </button>
        </div>
        <div role="tablist" aria-label="Agent replay" className="flex overflow-x-auto border-t border-white/10">
          {AGENTS.map((item) => {
            const selected = item.id === agent.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setActive(item.id)}
                className={`shrink-0 border-r border-white/10 px-3.5 py-2 font-mono text-[0.68rem] transition-colors ${
                  selected ? "bg-white/[0.07] text-term-text" : "text-term-dim hover:text-term-text"
                }`}
              >
                {item.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="border-b border-white/10 px-4 py-2 font-mono text-[0.68rem] text-term-dim sm:px-5">
        {agent.surface} · representative flow, values illustrative
      </div>

      <div
        className="min-h-[27.5rem] space-y-1 px-4 py-4 font-mono text-[0.72rem] leading-relaxed sm:min-h-[26rem] sm:px-5 sm:text-[0.78rem]"
        aria-live="off"
      >
        {agent.script.slice(0, shown).map((line, index) => (
          <Row key={`${agent.id}-${index}`} line={line} />
        ))}
        {!done && <span className="caret inline-block h-4 w-2 translate-y-0.5 bg-term-text/70" aria-hidden="true" />}
      </div>

      <div className="border-t border-white/10 px-4 py-3 font-mono text-[0.68rem] text-term-dim sm:px-5">
        memory → route → observe → pivot → verify → learn
      </div>
    </figure>
  );
}
