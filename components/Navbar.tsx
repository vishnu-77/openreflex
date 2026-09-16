"use client";

import { Coffee, Menu, X } from "lucide-react";
import { GithubIcon } from "./GithubIcon";
import { useState } from "react";
import { LINKS } from "@/lib/site";
import { Wordmark } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { ViewToggle } from "./ViewToggle";

const BUILDER_SECTIONS = [
  { href: "/#how", label: "How it works" },
  { href: "/#quickstart", label: "Quickstart" },
  { href: "/impact", label: "Impact" },
  { href: "/#privacy", label: "Privacy" },
  { href: "/docs", label: "Docs" },
];

const RESEARCH_SECTIONS = [
  { href: "/#idea", label: "The idea" },
  { href: "/#graph", label: "Graph explorer" },
  { href: "/#evidence", label: "Research" },
  { href: "/impact", label: "Impact" },
  { href: "/#prior-work", label: "Prior work" },
  { href: "/docs", label: "Docs" },
];

const VIEWS = [
  { className: "view-builder", sections: BUILDER_SECTIONS },
  { className: "view-research", sections: RESEARCH_SECTIONS },
];

export function Navbar({ showViewToggle = true }: { showViewToggle?: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur-md">
      <nav className="mx-auto flex h-16 max-w-[1320px] items-center justify-between gap-6 px-5 sm:px-10" aria-label="Main">
        <a href="/" className="rounded" aria-label="OpenReflex home">
          <Wordmark className="h-[26px] w-auto" />
        </a>

        {VIEWS.map((view) => (
          <ul key={view.className} className={`${view.className} hidden items-center gap-7 text-[0.93rem] text-muted xl:flex`}>
            {view.sections.map((section) => (
              <li key={section.href}>
                <a href={section.href} className="transition-colors hover:text-ink">
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        ))}

        <div className="flex items-center gap-2">
          {showViewToggle && <ViewToggle className="hidden md:flex" />}
          <ThemeToggle />
          <a
            href={LINKS.coffee}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden h-9 items-center gap-2 rounded-md border border-line px-3 text-sm text-text transition-colors hover:border-line-strong hover:text-ink sm:flex"
          >
            <Coffee size={15} aria-hidden="true" />
            Support
          </a>
          <a
            href={LINKS.github}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden h-9 items-center gap-2 rounded-md bg-ink px-3.5 text-sm font-medium text-bg transition-opacity hover:opacity-90 sm:flex"
          >
            <GithubIcon size={15} />
            GitHub
          </a>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-line text-muted xl:hidden"
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X size={17} /> : <Menu size={17} />}
          </button>
        </div>
      </nav>

      {open && (
        <div id="mobile-menu" className="border-t border-line bg-bg px-5 pb-5 pt-4 xl:hidden">
          {showViewToggle && <ViewToggle className="mb-2 w-full md:hidden [&>button]:flex-1 [&>button]:justify-center" />}
          {VIEWS.map((view) => (
            <ul key={view.className} className={`${view.className} flex flex-col text-[1.02rem]`}>
              {view.sections.map((section) => (
                <li key={section.href}>
                  <a href={section.href} onClick={() => setOpen(false)} className="block border-b border-line py-3 text-text">
                    {section.label}
                  </a>
                </li>
              ))}
            </ul>
          ))}
          <div className="mt-4 grid grid-cols-2 gap-2">
            <a
              href={LINKS.coffee}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-11 items-center justify-center gap-2 rounded-md border border-line text-sm text-text"
            >
              <Coffee size={15} aria-hidden="true" />
              Buy me a coffee
            </a>
            <a
              href={LINKS.github}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-11 items-center justify-center gap-2 rounded-md bg-ink text-sm font-medium text-bg"
            >
              <GithubIcon size={15} />
              GitHub
            </a>
          </div>
        </div>
      )}
    </header>
  );
}
