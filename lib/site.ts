export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://openreflex.vercel.app";

export const LINKS = {
  github: "https://github.com/vishnu-77/openreflex",
  issues: "https://github.com/vishnu-77/openreflex/issues",
  pypi: "https://pypi.org/project/openreflex/",
  ci: "https://github.com/vishnu-77/openreflex/actions/workflows/ci.yml",
  license: "https://github.com/vishnu-77/openreflex/blob/main/LICENSE",
  readme: "https://github.com/vishnu-77/openreflex#readme",
  liveTests: "https://github.com/vishnu-77/openreflex/blob/main/scripts/live_claude_code.py",
  coffee: "https://buymeacoffee.com/vishnuprashanth",
} as const;

export const RESEARCH_SOURCES = {
  claudeMem: { label: "claude-mem (GitHub)", href: "https://github.com/thedotmack/claude-mem" },
  mem0: { label: "Mem0 for Claude Code (docs)", href: "https://docs.mem0.ai/integrations/claude-code" },
  reasoningBank: { label: "ReasoningBank (arXiv 2509.25140)", href: "https://arxiv.org/abs/2509.25140" },
  awm: { label: "Agent Workflow Memory (arXiv 2409.07429)", href: "https://arxiv.org/abs/2409.07429" },
  ace: { label: "Agentic Context Engineering (arXiv 2510.04618)", href: "https://arxiv.org/abs/2510.04618" },
  reflexion: { label: "Reflexion (arXiv 2303.11366)", href: "https://arxiv.org/abs/2303.11366" },
  openhands: { label: "OpenHands Stuck Detector (docs)", href: "https://docs.openhands.dev/sdk/guides/agent-stuck-detector" },
} as const;

export const TAGLINE = "Muscle memory for AI coding agents";

export const TITLE = "OpenReflex: muscle memory for AI coding agents";

export const DESCRIPTION =
  "OpenReflex learns from every task your coding agent finishes and hands the next one what worked: the approach, " +
  "the files that mattered, and the fix for the last error. It flags failure loops live and runs entirely on your machine.";
