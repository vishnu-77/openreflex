import { ArrowUpRight } from "lucide-react";
import { LINKS } from "@/lib/site";
import { SectionHeader } from "./SectionHeader";

const FACTS = [
  {
    title: "On PyPI",
    body: "Install with pipx, uv or pip. The package is called openreflex.",
    link: { href: LINKS.pypi, label: "View on PyPI" },
  },
  {
    title: "Works with four agents",
    body: "Claude Code, Codex, Cursor and OpenCode, through lifecycle hooks and an MCP server with seven tools.",
    link: { href: LINKS.readme, label: "Read the setup guide" },
  },
  {
    title: "Verified in real Claude Code sessions",
    body: "An end-to-end suite drives headless Claude Code and checks that context and alerts actually reach the model.",
    link: { href: LINKS.liveTests, label: "See the test harness" },
  },
  {
    title: "Tested on Linux, macOS and Windows",
    body: "Every change runs the full suite on Python 3.11, 3.12 and 3.13, plus a clean install of the built package.",
    link: { href: LINKS.ci, label: "View CI" },
  },
  {
    title: "Runs locally",
    body: "One SQLite file per project, no background service, and hooks that never block your agent.",
    link: { href: "#privacy", label: "How data is handled" },
  },
  {
    title: "MIT licensed",
    body: "Open source and free to use, modify and ship.",
    link: { href: LINKS.license, label: "Read the license" },
  },
];

export function Shipped() {
  return (
    <section id="shipped" aria-labelledby="shipped-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="shipped"
          title="What's shipped"
          intro="OpenReflex 0.1 is available today. Here is what you get."
        />
        <dl className="grid sm:grid-cols-2 lg:grid-cols-3">
          {FACTS.map((fact) => {
            const external = fact.link.href.startsWith("http");
            return (
              <div key={fact.title} className="flex flex-col border-b border-line py-7 sm:pr-10">
                <dt className="text-[1.15rem] font-semibold tracking-tight text-ink">{fact.title}</dt>
                <dd className="mt-2 flex-1 leading-[1.7] text-muted">{fact.body}</dd>
                <dd className="mt-4">
                  <a
                    href={fact.link.href}
                    {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                    className="inline-flex items-center gap-1 text-[0.93rem] text-accent underline-offset-4 hover:underline"
                  >
                    {fact.link.label}
                    {external && <ArrowUpRight size={14} aria-hidden="true" />}
                  </a>
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </section>
  );
}
