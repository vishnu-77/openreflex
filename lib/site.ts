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

export const TAGLINE = "Muscle memory for AI coding agents";

export const TITLE = "OpenReflex: muscle memory for AI coding agents";

export const DESCRIPTION =
  "OpenReflex learns from every task your coding agent finishes and hands the next one what worked: the approach, " +
  "the files that mattered, and the fix for the last error. It flags failure loops live and runs entirely on your machine.";
