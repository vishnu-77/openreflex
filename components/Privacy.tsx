import { Check, X } from "lucide-react";
import { SectionHeader } from "./SectionHeader";

const KEPT = [
  "Tool names and a coarse category, such as read, edit or test",
  "A fingerprint of each call's arguments, so repeats can be spotted",
  "File paths inside the project",
  "Whether a call passed or failed, and a short masked error line",
  "Your prompt as the task description, with keys and tokens redacted",
];

const NEVER = [
  "The contents of your files",
  "The commands your agent ran",
  "Tool output and logs",
  "Conversation transcripts",
  "Anything outside the project folder",
];

export function Privacy() {
  return (
    <section id="privacy" aria-labelledby="privacy-title" className="border-b border-line bg-bg-soft">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="privacy"
          title="Private by design"
          intro="OpenReflex is a local SQLite database on your machine. There is no account, no server and no telemetry, and capture stays off until you enable a project."
        />
        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2">
          <div className="bg-panel p-6 sm:p-8">
            <h3 className="text-lg font-semibold text-ink">What it keeps</h3>
            <ul className="mt-5 space-y-3.5">
              {KEPT.map((item) => (
                <li key={item} className="flex gap-3 leading-relaxed text-text">
                  <Check size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-panel p-6 sm:p-8">
            <h3 className="text-lg font-semibold text-ink">What it never keeps</h3>
            <ul className="mt-5 space-y-3.5">
              {NEVER.map((item) => (
                <li key={item} className="flex gap-3 leading-relaxed text-text">
                  <X size={18} className="mt-0.5 shrink-0 text-fail" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-6 max-w-[48rem] leading-relaxed text-muted">
          Stop capture with <code className="font-mono text-[0.9em] text-ink">openreflex revoke</code>, delete a
          project&apos;s data with <code className="font-mono text-[0.9em] text-ink">openreflex forget --yes</code>, or turn
          it off everywhere with <code className="font-mono text-[0.9em] text-ink">OPENREFLEX_DISABLE=1</code>.
        </p>
      </div>
    </section>
  );
}
