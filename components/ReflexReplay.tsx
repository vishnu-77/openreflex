"use client";

import { RotateCcw } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

type Kind = "cmd" | "tool" | "fail" | "ok" | "alert" | "context" | "lesson" | "divider";
type Line = { kind: Kind; text: string; detail?: string; pause?: number };

// Mirrors a real session captured in OpenReflex's live Claude Code test suite.
const SCRIPT: Line[] = [
  { kind: "cmd", text: 'claude "fix parse_date returning the wrong month"', pause: 700 },
  { kind: "tool", text: "Read   dates.py" },
  { kind: "fail", text: "Bash   python -m pytest -q", detail: "1 failed" },
  { kind: "fail", text: "Bash   python -m pytest -q", detail: "1 failed" },
  { kind: "fail", text: "Bash   python -m pytest -q", detail: "1 failed", pause: 500 },
  {
    kind: "alert",
    text: "OpenReflex: 3 consecutive tool failures. Stop retrying the same fix and re-read the error.",
    pause: 1300,
  },
  { kind: "tool", text: "Edit   dates.py" },
  { kind: "ok", text: "Bash   python -m pytest -q", detail: "2 passed", pause: 500 },
  { kind: "lesson", text: "learned: this failure was resolved by an edit in dates.py", pause: 1200 },
  { kind: "divider", text: "next session", pause: 900 },
  { kind: "cmd", text: 'claude "parse_date is off by one for January dates"', pause: 600 },
  { kind: "context", text: "[OpenReflex] debug task, 1 similar past task, 1 succeeded" },
  { kind: "context", text: "Likely relevant files: dates.py, tests/test_dates.py", pause: 900 },
  { kind: "tool", text: "Edit   dates.py" },
  { kind: "ok", text: "Bash   python -m pytest -q", detail: "2 passed" },
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
        <p className="my-1.5 border-l-2 border-[#e7b25a] bg-[#e7b25a]/10 py-1.5 pl-3 pr-2 text-[#f1c983]">{line.text}</p>
      );
    case "context":
      return <p className="border-l-2 border-[#7cc9c8] pl-3 text-[#9edce0]">{line.text}</p>;
    case "lesson":
      return <p className="pl-3 text-[#9edce0]/80">{line.text}</p>;
    default: {
      const tone = line.kind === "fail" ? "text-[#f08a78]" : line.kind === "ok" ? "text-[#8fcf8f]" : "";
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
  const reduceMotion = useReducedMotion();
  const [shown, setShown] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const play = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setShown(0);
    let index = 0;
    const step = () => {
      index += 1;
      setShown(index);
      if (index < SCRIPT.length) timer.current = setTimeout(step, SCRIPT[index - 1].pause ?? 420);
    };
    timer.current = setTimeout(step, 500);
  }, []);

  useEffect(() => {
    if (reduceMotion) {
      setShown(SCRIPT.length);
      return;
    }
    play();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [play, reduceMotion]);

  const done = shown >= SCRIPT.length;

  return (
    <figure className="overflow-hidden rounded-lg border border-line-strong/60 bg-term shadow-[0_24px_60px_-28px_rgba(0,0,0,0.55)]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
        </div>
        <figcaption className="font-mono text-[0.72rem] text-term-dim">claude code, with openreflex hooks</figcaption>
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
      <div
        className="min-h-[27.5rem] space-y-1 px-4 py-4 font-mono text-[0.74rem] leading-relaxed sm:min-h-[26rem] sm:px-5 sm:text-[0.8rem]"
        aria-live="off"
      >
        {SCRIPT.slice(0, shown).map((line, index) => (
          <Row key={index} line={line} />
        ))}
        {!done && <span className="caret inline-block h-4 w-2 translate-y-0.5 bg-term-text/70" aria-hidden="true" />}
      </div>
    </figure>
  );
}
