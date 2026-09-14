export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://openreflex.cc";

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

// Papers quoted in the Researcher view's evidence section. Separate from RESEARCH_SOURCES, which lists compared work.
export const EVIDENCE_SOURCES = {
  trajectories: {
    authors: "Majgaonkar, Fei, Li, Sarro and Ye",
    year: 2025,
    title: "Understanding Code Agent Behaviour: An Empirical Study of Success and Failure Trajectories",
    id: "arXiv:2511.00197",
    href: "https://arxiv.org/abs/2511.00197",
  },
  failures: {
    authors: "Liu, Liu, Li, Tan, Zhu, Lian and Zhang",
    year: 2025,
    title: "An Empirical Study on Failures in Automated Issue Solving",
    id: "arXiv:2509.13941",
    href: "https://arxiv.org/abs/2509.13941",
  },
  reflexion: {
    authors: "Shinn, Cassano, Berman, Gopinath, Narasimhan and Yao",
    year: 2023,
    title: "Reflexion: Language Agents with Verbal Reinforcement Learning",
    id: "arXiv:2303.11366",
    href: "https://arxiv.org/abs/2303.11366",
  },
} as const;

export const TAGLINE = "Muscle memory for AI coding agents";

export const TITLE = "OpenReflex: AI Coding Agents That Learn From Every Task";

export const DESCRIPTION =
  "Open-source plugin for Claude Code, Codex, Cursor and OpenCode. Recommends efficient paths from past tasks, says when to pivot or stop, and keeps data local.";
