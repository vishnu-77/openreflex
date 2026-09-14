// Integration guides. Every statement mirrors how the adapters in the openreflex package actually work.

export type GuideStep = { note: string; command?: string };
export type GuideFaq = { q: string; a: string };

export type Guide = {
  slug: "claude-code" | "codex" | "cursor" | "opencode";
  agent: string;
  title: string; // <title>, under ~60 characters
  description: string; // meta description, under ~155 characters
  h1: string;
  lead: string;
  benefits: { title: string; body: string }[];
  install: GuideStep[];
  alternative?: { heading: string; steps: GuideStep[] };
  events: { event: string; what: string }[];
  notes: string[];
  faq: GuideFaq[];
  verified: boolean;
};

const INSTALL: GuideStep = { note: "Install the OpenReflex CLI (Python 3.11 or newer)", command: "pipx install openreflex" };

export const GUIDES: Guide[] = [
  {
    slug: "claude-code",
    agent: "Claude Code",
    title: "OpenReflex for Claude Code: Hooks That Learn",
    description:
      "Make Claude Code learn from every task. OpenReflex adds lifecycle hooks and an MCP server that reuse past fixes and catch failure loops, locally.",
    h1: "OpenReflex for Claude Code",
    lead:
      "OpenReflex plugs into Claude Code's lifecycle hooks and MCP. It records how each task went, hands the next similar task what worked, and interrupts " +
      "only when Claude is stuck retrying the same failing step. Everything stays in a local SQLite file.",
    benefits: [
      { title: "Context before the first tool call", body: "Similar past tasks, the files that mattered and known fixes arrive as additional context when you submit a prompt." },
      { title: "Loop alerts while it works", body: "Repeated failing commands, identical retries or stalled progress raise one specific alert with a different approach to try." },
      { title: "Lessons checked by your tests", body: "A task only counts as a success when a test, lint or build passes after the last edit, so guesses never become advice." },
    ],
    install: [
      INSTALL,
      { note: "Add the OpenReflex plugin marketplace", command: "claude plugin marketplace add vishnu-77/openreflex" },
      { note: "Install the plugin", command: "claude plugin install openreflex@openreflex" },
      { note: "Enable it in each project you want it to learn from", command: "openreflex approve" },
    ],
    alternative: {
      heading: "Prefer project settings over a plugin?",
      steps: [INSTALL, { note: "Write hooks to .claude/settings.json and the MCP server to .mcp.json", command: "openreflex install claude-code" }],
    },
    events: [
      { event: "UserPromptSubmit", what: "Starts a task and injects the Execution Context when relevant experience exists." },
      { event: "PreToolUse / PostToolUse", what: "Records each tool call's category, files and result; alerts are returned as additional context." },
      { event: "PostToolUseFailure", what: "Records the failure and a masked, one-line error signature." },
      { event: "PreCompact", what: "Notes context compaction, a signal of runaway context growth." },
      { event: "Stop / SessionEnd", what: "Works out the outcome and stores lessons from the task." },
    ],
    notes: [
      "The MCP server adds tools Claude can call directly: get_execution_context, choose_path, record_outcome, search_experience, explain_node and project_insights.",
      "Claude Code is verified in live, headless sessions by OpenReflex's end-to-end test suite.",
    ],
    faq: [
      { q: "Does OpenReflex send my code or conversation to a model?", a: "No. It learns deterministically from hook metadata and never stores file contents, commands, tool output or transcripts." },
      { q: "Will it slow Claude Code down?", a: "Each hook is a short local process that always exits cleanly and never blocks Claude, even if something goes wrong." },
      { q: "How do I turn it off?", a: "Run openreflex revoke in the project, or set OPENREFLEX_DISABLE=1 to disable capture everywhere." },
    ],
    verified: true,
  },
  {
    slug: "codex",
    agent: "Codex",
    title: "OpenReflex for OpenAI Codex CLI: Learning Hooks",
    description:
      "Give OpenAI Codex CLI a memory of what worked. OpenReflex adds hooks and an MCP server that reuse past fixes and flag failure loops, all locally.",
    h1: "OpenReflex for OpenAI Codex CLI",
    lead:
      "OpenReflex connects to Codex through its hooks and MCP support. Lessons learned in any agent working on the project, including Claude Code, are " +
      "offered to Codex before a similar task starts.",
    benefits: [
      { title: "Shared project memory", body: "Codex reads from the same local Experience Graph as your other agents, so a fix found elsewhere is not rediscovered." },
      { title: "Failure loops caught", body: "Codex reports failures inside tool results; OpenReflex reads exit codes from them and alerts when a loop forms." },
      { title: "Private by design", body: "Only tool categories, project-relative paths, pass or fail and masked error lines are kept." },
    ],
    install: [
      INSTALL,
      { note: "Write hooks to .codex/hooks.json and the MCP server to .codex/config.toml", command: "openreflex install codex" },
      { note: "Open /hooks in Codex once and trust the OpenReflex entries" },
    ],
    alternative: {
      heading: "Install as a Codex plugin instead",
      steps: [INSTALL, { note: "Add the plugin marketplace, then enable the plugin in Codex", command: "codex plugin marketplace add vishnu-77/openreflex" }, { note: "Enable each project", command: "openreflex approve" }],
    },
    events: [
      { event: "UserPromptSubmit", what: "Starts a task and injects the Execution Context when relevant experience exists." },
      { event: "PreToolUse / PostToolUse", what: "Records each tool call; failures are detected from the exit code in the tool response." },
      { event: "PreCompact", what: "Notes context compaction." },
      { event: "Stop / SessionEnd", what: "Works out the outcome and stores lessons." },
    ],
    notes: [
      "Codex asks you to trust new hooks once. Until then, the hooks do not run.",
      "The Codex integration follows Codex's documented hook protocol and is covered by OpenReflex's protocol and fuzz tests.",
    ],
    faq: [
      { q: "Can Codex use lessons learned in Claude Code?", a: "Yes. All agents in a project share one local Experience Graph." },
      { q: "Where is the data stored?", a: "In ~/.openreflex/projects/<hash>/experience.sqlite3 on your machine." },
    ],
    verified: false,
  },
  {
    slug: "cursor",
    agent: "Cursor",
    title: "OpenReflex for Cursor: Agent Hooks That Learn",
    description:
      "Help Cursor's agent learn from every task. OpenReflex adds Cursor hooks and an MCP server that reuse past fixes and flag failure loops, locally.",
    h1: "OpenReflex for Cursor",
    lead:
      "OpenReflex uses Cursor's agent hooks and MCP support to learn from each task in your project and bring what worked into the next one.",
    benefits: [
      { title: "Context on the first tool result", body: "Cursor cannot add context when a prompt is submitted, so OpenReflex delivers it with the agent's first tool result instead." },
      { title: "Alerts where Cursor listens", body: "Loop and stagnation alerts are returned as additional context after tool calls." },
      { title: "No double counting", body: "If Cursor also runs Claude Code hook configs, those events are attributed to Cursor and de-duplicated." },
    ],
    install: [
      INSTALL,
      { note: "Write hooks to .cursor/hooks.json and the MCP server to .cursor/mcp.json", command: "openreflex install cursor" },
    ],
    events: [
      { event: "beforeSubmitPrompt", what: "Starts a task; the Execution Context is held until the first tool result." },
      { event: "preToolUse / postToolUse", what: "Records each tool call and returns context or alerts after it." },
      { event: "postToolUseFailure", what: "Records the failure and a masked error signature." },
      { event: "stop / sessionEnd", what: "Works out the outcome and stores lessons." },
    ],
    notes: [
      "OpenReflex never grants or denies tool permissions in Cursor; it only observes and advises.",
      "The Cursor integration follows Cursor's documented hook protocol and is covered by OpenReflex's protocol and fuzz tests.",
    ],
    faq: [
      { q: "Why does context appear after the first tool call?", a: "Cursor's beforeSubmitPrompt hook cannot inject context, so the first tool result is the earliest point OpenReflex can reach the model." },
      { q: "Does it work with other agents in the same repo?", a: "Yes. Cursor shares one local Experience Graph with Claude Code, Codex and OpenCode." },
    ],
    verified: false,
  },
  {
    slug: "opencode",
    agent: "OpenCode",
    title: "OpenReflex for OpenCode: Plugin & MCP Setup",
    description:
      "Add learning to OpenCode. The OpenReflex plugin and MCP server reuse past fixes, flag failure loops and keep all data on your machine.",
    h1: "OpenReflex for OpenCode",
    lead:
      "OpenReflex installs a small OpenCode plugin that forwards session events to the local OpenReflex engine, plus an MCP server for direct queries.",
    benefits: [
      { title: "Context in the system prompt", body: "Relevant experience is added to the system prompt for the turn it applies to." },
      { title: "Alerts in tool output", body: "Loop alerts are appended to the output of the tool call that triggered them." },
      { title: "Failures captured", body: "Tool errors are read from OpenCode's message events, since the after-tool hook only runs on success." },
    ],
    install: [
      INSTALL,
      { note: "Add .opencode/plugins/openreflex.ts and the MCP server to opencode.json", command: "openreflex install opencode" },
    ],
    events: [
      { event: "chat.message", what: "Starts a task and prepares the Execution Context." },
      { event: "tool.execute.before / after", what: "Records each tool call and appends alerts to its output." },
      { event: "message.part.updated (error)", what: "Records failed tool calls." },
      { event: "session.idle / session.compacted", what: "Stores the outcome and lessons, and notes compaction." },
    ],
    notes: [
      "If your project uses opencode.jsonc, add the MCP entry manually; OpenReflex does not rewrite JSONC files.",
      "The OpenCode integration follows OpenCode's plugin API and is covered by OpenReflex's protocol and fuzz tests.",
    ],
    faq: [
      { q: "Does the plugin need network access?", a: "No. It runs the local openreflex command and never contacts a server." },
      { q: "Can I use only the MCP tools?", a: "Yes. The MCP server works on its own, though live capture and alerts need the plugin." },
    ],
    verified: false,
  },
];

export const guideBySlug = (slug: string) => GUIDES.find((guide) => guide.slug === slug);
