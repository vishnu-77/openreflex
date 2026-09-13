"use client";

import { useEffect, useState } from "react";
import { currentView, setView, VIEW_EVENT, type View } from "@/lib/view";

export function ViewToggle({ className = "" }: { className?: string }) {
  const [view, setState] = useState<View>("builder");

  useEffect(() => {
    setState(currentView());
    const onChange = (event: Event) => setState((event as CustomEvent<View>).detail);
    window.addEventListener(VIEW_EVENT, onChange);
    return () => window.removeEventListener(VIEW_EVENT, onChange);
  }, []);

  // Pressed styling comes from the html data-view attribute (research: variant), so it is right before hydration.
  const base = "flex h-full items-center px-3 text-sm transition-colors hover:text-ink";
  return (
    <div role="group" aria-label="Page view" className={`flex h-9 overflow-hidden rounded-md border border-line ${className}`}>
      <button
        type="button"
        aria-pressed={view === "builder"}
        onClick={() => setView("builder")}
        className={`${base} bg-panel font-medium text-ink research:bg-transparent research:font-normal research:text-muted`}
      >
        Builder
      </button>
      <button
        type="button"
        aria-pressed={view === "research"}
        onClick={() => setView("research")}
        className={`${base} border-l border-line text-muted research:bg-panel research:font-medium research:text-ink`}
      >
        Researcher
      </button>
    </div>
  );
}

export function ResearchLink() {
  return (
    <button type="button" onClick={() => setView("research")} className="text-accent underline-offset-4 hover:underline">
      See the Researcher view
    </button>
  );
}
