"use client";

import { useState } from "react";
import { CopyButton } from "./CopyButton";
import { SectionHeader } from "./SectionHeader";

type Step = { note: string; command?: string; code?: string };
type Agent = { id: string; name: string; summary: string; guide: string; steps: Step[] };

const INSTALL: Step = { note: "Install the OpenReflex CLI", command: "pipx install openreflex" };

const AGENTS: Agent[] = [
  {
    id: "claude-plugin",
    guide: "/claude-code",
    name: "Claude Code",
    summary: "Plugin: hooks, MCP server and skill",
    steps: [
      INSTALL,
      { note: "Add the plugin marketplace", command: "claude plugin marketplace add vishnu-77/openreflex" },
      { note: "Install the plugin", command: "claude plugin install openreflex@openreflex" },
      { note: "Enable it in each project you want it to learn from", command: "openreflex approve" },
    ],
  },
  {
    id: "claude-project",
    guide: "/claude-code",
    name: "Claude Code (project)",
    summary: "Project settings, no plugin",
    steps: [INSTALL, { note: "Write hooks and MCP config into this project", command: "openreflex install claude-code" }],
  },
  {
    id: "codex",
    guide: "/codex",
    name: "Codex",
    summary: "Hooks and MCP in .codex/",
    steps: [
      INSTALL,
      { note: "Write hooks and MCP config into this project", command: "openreflex install codex" },
      { note: "Open /hooks in Codex once and trust the OpenReflex entries" },
    ],
  },
  {
    id: "cursor",
    guide: "/cursor",
    name: "Cursor",
    summary: "Hooks and MCP in .cursor/",
    steps: [INSTALL, { note: "Write hooks and MCP config into this project", command: "openreflex install cursor" }],
  },
  {
    id: "opencode",
    guide: "/opencode",
    name: "OpenCode",
    summary: "Plugin and MCP in opencode.json",
    steps: [INSTALL, { note: "Add the OpenReflex plugin and MCP server", command: "openreflex install opencode" }],
  },
  {
    id: "mcp",
    guide: "/docs#mcp",
    name: "Any MCP client",
    summary: "Tools only, no hooks",
    steps: [
      INSTALL,
      { note: "Enable the project", command: "openreflex approve" },
      {
        note: "Register the stdio server in your client's MCP config",
        code: '{\n  "mcpServers": {\n    "openreflex": { "command": "openreflex", "args": ["mcp"] }\n  }\n}',
      },
    ],
  },
];

export function Quickstart() {
  const [active, setActive] = useState(AGENTS[0].id);
  const agent = AGENTS.find((item) => item.id === active) ?? AGENTS[0];

  return (
    <section id="quickstart" aria-labelledby="quickstart-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="quickstart"
          title="Connect your agent"
          intro="Pick your agent. OpenReflex needs Python 3.11 or newer, and nothing is recorded until you enable a project."
        />

        <div className="grid overflow-hidden rounded-lg border border-line lg:grid-cols-[19rem_minmax(0,1fr)]">
          <div role="tablist" aria-label="Agents" aria-orientation="vertical" className="flex overflow-x-auto border-b border-line bg-bg-soft lg:flex-col lg:border-b-0 lg:border-r">
            {AGENTS.map((item) => {
              const selected = item.id === agent.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  id={`tab-${item.id}`}
                  aria-selected={selected}
                  aria-controls="quickstart-panel"
                  onClick={() => setActive(item.id)}
                  className={`shrink-0 border-l-2 px-5 py-4 text-left transition-colors lg:border-b lg:border-b-line lg:last:border-b-0 ${
                    selected ? "border-l-accent bg-panel" : "border-l-transparent hover:bg-panel/60"
                  }`}
                >
                  <span className={`block font-medium ${selected ? "text-ink" : "text-text"}`}>{item.name}</span>
                  <span className="mt-0.5 hidden text-[0.85rem] text-muted sm:block">{item.summary}</span>
                </button>
              );
            })}
          </div>

          <div id="quickstart-panel" role="tabpanel" aria-labelledby={`tab-${agent.id}`} className="bg-term p-5 sm:p-8">
            <ol className="space-y-6">
              {agent.steps.map((step, index) => (
                <li key={`${agent.id}-${index}`} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
                  <span className="pt-0.5 font-mono text-[0.8rem] tabular-nums text-term-dim">{index + 1}</span>
                  <div className="min-w-0">
                    <p className="text-[0.95rem] text-term-text/80">{step.note}</p>
                    {step.command && (
                      <div className="mt-2.5 flex items-center gap-3 rounded-md border border-white/10 bg-white/[0.03] py-1.5 pl-4 pr-1.5 font-mono text-[0.85rem] text-term-text">
                        <span className="select-none text-term-dim">$</span>
                        <code className="min-w-0 flex-1 break-all sm:overflow-x-auto sm:whitespace-nowrap sm:break-normal">{step.command}</code>
                        <CopyButton text={step.command} />
                      </div>
                    )}
                    {step.code && (
                      <div className="relative mt-2.5 rounded-md border border-white/10 bg-white/[0.03]">
                        <pre className="overflow-x-auto p-4 pr-12 font-mono text-[0.8rem] leading-relaxed text-term-text">
                          <code>{step.code}</code>
                        </pre>
                        <CopyButton text={step.code} label="Copy config" className="absolute right-1.5 top-1.5" />
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-8 border-t border-white/10 pt-5 font-mono text-[0.78rem] leading-relaxed text-term-dim">
              <a href={agent.guide} className="text-term-text underline underline-offset-4 hover:text-white">
                Full setup guide for {agent.name.replace(" (project)", "")}
              </a>
              <br />
              Check the setup any time with openreflex doctor. Claude Code is verified in live sessions; the other
              integrations follow each agent&apos;s documented hook protocol.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
