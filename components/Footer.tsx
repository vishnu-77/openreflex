import { Coffee } from "lucide-react";
import { LINKS, TAGLINE } from "@/lib/site";
import { Wordmark } from "./Logo";

const PROJECT = [
  { href: LINKS.github, label: "GitHub" },
  { href: LINKS.pypi, label: "PyPI" },
  { href: LINKS.issues, label: "Issues" },
  { href: LINKS.license, label: "MIT License" },
];

const PAGE = [
  { href: "#how", label: "How it works" },
  { href: "#quickstart", label: "Quickstart" },
  { href: "#privacy", label: "Privacy" },
  { href: "#shipped", label: "What's shipped" },
];

export function Footer() {
  return (
    <footer className="bg-bg-soft">
      <div className="mx-auto grid max-w-[1320px] gap-12 px-5 py-16 sm:px-10 md:grid-cols-[1.6fr_1fr_1fr_1.2fr]">
        <div>
          <Wordmark className="h-[30px] w-auto" />
          <p className="mt-4 max-w-[22rem] leading-relaxed text-muted">{TAGLINE}. Open source and local-first.</p>
        </div>

        <nav aria-label="Project links">
          <h2 className="text-sm font-semibold text-ink">Project</h2>
          <ul className="mt-4 space-y-2.5 text-muted">
            {PROJECT.map((link) => (
              <li key={link.href}>
                <a href={link.href} target="_blank" rel="noopener noreferrer" className="hover:text-ink">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <nav aria-label="On this page">
          <h2 className="text-sm font-semibold text-ink">On this page</h2>
          <ul className="mt-4 space-y-2.5 text-muted">
            {PAGE.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="hover:text-ink">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <h2 className="text-sm font-semibold text-ink">Support</h2>
          <p className="mt-4 leading-relaxed text-muted">If OpenReflex saves you time, you can support its development.</p>
          <a
            href={LINKS.coffee}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex h-10 items-center gap-2 rounded-md border border-line-strong px-4 text-sm text-ink transition-colors hover:bg-panel"
          >
            <Coffee size={15} aria-hidden="true" />
            Buy me a coffee
          </a>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-[1320px] px-5 py-6 text-sm text-muted sm:px-10">© 2026 vishnu-77. Released under the MIT License.</p>
      </div>
    </footer>
  );
}
