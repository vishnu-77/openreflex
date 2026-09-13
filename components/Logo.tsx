export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  // A reflex loop: an arc that returns to its origin, around a node.
  return (
    <svg viewBox="0 0 80 80" className={className} aria-hidden="true" focusable="false">
      <circle cx="40" cy="40" r="34" fill="none" stroke="var(--border-strong)" strokeWidth="2" />
      <path
        d="M40 15 A25 25 0 1 1 16.51 31.45"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        d="M8.88 36.22 L16.51 31.45 L19.29 40.01"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="40" cy="40" r="8" fill="var(--accent)" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      <span className="text-[1.15rem] font-semibold tracking-tight text-ink">OpenReflex</span>
    </span>
  );
}
