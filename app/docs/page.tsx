import { CopyButton } from "@/components/CopyButton";
import { JsonLd } from "@/components/JsonLd";
import { PageShell } from "@/components/PageShell";
import { GUIDES } from "@/lib/guides";
import { articleJsonLd, breadcrumbJsonLd, pageMetadata } from "@/lib/seo";
import { LINKS } from "@/lib/site";

const TITLE = "OpenReflex Docs: Install, CLI, MCP Tools & Privacy";
const DESCRIPTION =
  "Install OpenReflex for Claude Code, Codex, Cursor or OpenCode, then use its CLI and MCP tools. Covers enabling projects, privacy and troubleshooting.";

export const metadata = pageMetadata({ title: TITLE, description: DESCRIPTION, path: "/docs" });

const CLI = [
  ["openreflex install <agent>", "Write hooks and MCP config for claude-code, codex, cursor or opencode, and enable the project. Add --dry-run to preview."],
  ["openreflex approve", "Enable capture for the current project (needed after a plugin install)."],
  ["openreflex revoke", "Disable capture for the current project. Existing data is kept."],
  ["openreflex context \"<task>\"", "Preview the Execution Context a task would receive, without recording anything."],
  ["openreflex status [--json]", "Show what has been captured, reused and learned in this project."],
  ["openreflex doctor", "Check the installation and show recent hook errors."],
  ["openreflex forget --yes", "Delete all captured data for the project."],
  ["openreflex benchmark", "Run the simulated benchmark suite."],
  ["openreflex mcp", "Start the MCP server over stdio (used by agent configs)."],
];

const MCP_TOOLS = [
  ["get_execution_context", "Retrieve relevant past experience, candidate strategies (dominated ones marked), an execution budget, likely files and lessons for a task. Optional max_tool_calls, max_minutes and max_context_tokens limit the plan."],
  ["choose_path", "Declare the strategy the agent is following, so the outcome is compared against the right plan."],
  ["check_progress", "Estimate whether more work on the current path is worth it, and recommend continue, pivot or stop."],
  ["record_outcome", "Record a verified outcome, such as tests passing, with short evidence."],
  ["search_experience", "Search past tasks in the project by description."],
  ["explain_node", "Show an Experience Graph node and its relations."],
  ["project_insights", "Summarise capture, reuse, outcomes and learning for the project."],
  ["approve_project", "Enable the project, only when the user explicitly asks."],
];

function Command({ command }: { command: string }) {
  return (
    <div className="mt-3 flex items-center gap-3 rounded-md bg-term py-1.5 pl-4 pr-1.5 font-mono text-[0.88rem] text-term-text">
      <span className="select-none text-term-dim">$</span>
      <code className="min-w-0 flex-1 break-all sm:break-normal">{command}</code>
      <CopyButton text={command} />
    </div>
  );
}

function RefTable({ head, rows }: { head: [string, string]; rows: string[][] }) {
  return (
    <div className="mt-6 overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[560px] border-collapse text-left">
        <thead className="bg-panel">
          <tr className="text-[0.88rem] text-muted">
            <th scope="col" className="w-[38%] px-5 py-3 font-medium">{head[0]}</th>
            <th scope="col" className="px-5 py-3 font-medium">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, what]) => (
            <tr key={name} className="border-t border-line align-top">
              <td className="px-5 py-3 font-mono text-[0.86rem] text-ink">{name}</td>
              <td className="px-5 py-3 leading-relaxed text-text">{what}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SECTIONS = [
  { id: "install", label: "Install" },
  { id: "agents", label: "Set up your agent" },
  { id: "cli", label: "CLI reference" },
  { id: "mcp", label: "MCP tools" },
  { id: "privacy", label: "Privacy and data" },
  { id: "troubleshooting", label: "Troubleshooting" },
];

export default function DocsPage() {
  const crumbs = [
    { name: "Home", path: "/" },
    { name: "Docs", path: "/docs" },
  ];
  const h2 = "scroll-mt-24 text-[1.6rem] font-semibold tracking-tight text-ink";
  return (
    <PageShell crumbs={crumbs}>
      <JsonLd data={[articleJsonLd({ title: TITLE, description: DESCRIPTION, path: "/docs" }), breadcrumbJsonLd(crumbs)]} />
      <article>
        <header className="mt-8 border-b border-line pb-10">
          <p className="font-mono text-[0.8rem] text-accent">Documentation</p>
          <h1 className="mt-4 font-serif text-[2.6rem] leading-[1.05] tracking-[-0.02em] text-ink sm:text-[3.4rem]">OpenReflex docs</h1>
          <p className="mt-6 max-w-[46rem] text-[1.08rem] leading-[1.75] text-muted">
            OpenReflex is an open-source plugin that helps AI coding agents learn from every task. It reuses what worked,
            catches failure loops while they happen, and keeps everything on your machine.
          </p>
          <nav aria-label="On this page" className="mt-8">
            <ul className="flex flex-wrap gap-2">
              {SECTIONS.map((section) => (
                <li key={section.id}>
                  <a href={`#${section.id}`} className="inline-flex h-9 items-center rounded-md border border-line px-3 text-[0.92rem] text-text hover:border-line-strong hover:text-ink">
                    {section.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <section className="mt-12">
          <h2 id="install" className={h2}>Install</h2>
          <p className="mt-3 leading-relaxed text-text">OpenReflex needs Python 3.11 or newer. Install the CLI with pipx, uv or pip.</p>
          <Command command="pipx install openreflex" />
          <p className="mt-4 leading-relaxed text-muted">
            Then install it for your agent. Nothing is recorded until a project is enabled; <code className="font-mono text-[0.9em] text-ink">openreflex install</code> enables
            the project for you.
          </p>
        </section>

        <section className="mt-14">
          <h2 id="agents" className={h2}>Set up your agent</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {GUIDES.map((guide) => (
              <a key={guide.slug} href={`/${guide.slug}`} className="block rounded-lg border border-line bg-panel p-5 hover:border-line-strong">
                <span className="block font-semibold text-ink">OpenReflex for {guide.agent}</span>
                <span className="mt-1 block leading-relaxed text-muted">{guide.description}</span>
              </a>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <h2 id="cli" className={h2}>CLI reference</h2>
          <RefTable head={["Command", "What it does"]} rows={CLI} />
        </section>

        <section className="mt-14">
          <h2 id="mcp" className={h2}>MCP tools</h2>
          <p className="mt-3 leading-relaxed text-text">
            The OpenReflex MCP server runs over stdio. Agent installs register it automatically; any other MCP client can add it:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-md bg-term px-4 py-3 font-mono text-[0.86rem] leading-relaxed text-term-text">
            <code>{'{\n  "mcpServers": {\n    "openreflex": { "command": "openreflex", "args": ["mcp"] }\n  }\n}'}</code>
          </pre>
          <RefTable head={["Tool", "What it does"]} rows={MCP_TOOLS} />
          <p className="mt-6 leading-relaxed text-text">
            To limit every task without an MCP call, set <code className="font-mono text-[0.9em]">OPENREFLEX_BUDGET</code>,
            for example <code className="font-mono text-[0.9em]">calls=40,minutes=20,tokens=60000</code>. The recommended
            path is the best one that fits, and the execution budget never exceeds these limits.
          </p>
        </section>

        <section className="mt-14">
          <h2 id="privacy" className={h2}>Privacy and data</h2>
          <ul className="mt-4 space-y-3 leading-relaxed text-text">
            <li><strong className="font-semibold text-ink">Kept:</strong> tool names and categories, a fingerprint of each call&apos;s arguments, project-relative file paths, pass or fail, duration, output size, and a masked one-line error signature.</li>
            <li><strong className="font-semibold text-ink">Never kept:</strong> file contents, command text, tool output, transcripts, or paths outside the project.</li>
            <li><strong className="font-semibold text-ink">Prompts:</strong> stored as a task description of up to 1,000 characters, with keys and tokens redacted.</li>
            <li>
              <strong className="font-semibold text-ink">Location:</strong> <code className="font-mono text-[0.9em]">~/.openreflex/projects/&lt;hash&gt;/experience.sqlite3</code>.
              Set <code className="font-mono text-[0.9em]">OPENREFLEX_HOME</code> to move it or <code className="font-mono text-[0.9em]">OPENREFLEX_DISABLE=1</code> to turn capture off everywhere.
            </li>
          </ul>
        </section>

        <section className="mt-14">
          <h2 id="troubleshooting" className={h2}>Troubleshooting</h2>
          <dl className="mt-4">
            {[
              ["Nothing is being captured", "Run openreflex doctor. Check the project is enabled (openreflex approve) and that the openreflex command is on your PATH."],
              ["Hooks seem to do nothing in Codex", "Open /hooks in Codex and trust the OpenReflex entries; untrusted hooks do not run."],
              ["Where are hook errors logged?", "In ~/.openreflex/logs/errors.log. Hooks never block your agent, so errors are recorded there instead of shown."],
              ["No context was injected", "Context is only added when relevant past experience exists, so a new project starts silent."],
            ].map(([q, a]) => (
              <div key={q} className="border-t border-line py-5">
                <dt className="font-semibold text-ink">{q}</dt>
                <dd className="mt-2 leading-relaxed text-muted">{a}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-muted">
            Still stuck? <a href={LINKS.issues} className="text-accent underline underline-offset-4">Open an issue on GitHub</a>.
          </p>
        </section>
      </article>
    </PageShell>
  );
}
