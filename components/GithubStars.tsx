"use client";

import { useEffect, useState } from "react";

// Shows the live star count once it is meaningful; stays hidden if the GitHub API is unavailable.
export function GithubStars() {
  const [stars, setStars] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("https://api.github.com/repos/vishnu-77/openreflex", { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data && typeof data.stargazers_count === "number") setStars(data.stargazers_count);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  if (stars === null || stars < 10) return null;
  return (
    <span className="ml-1 rounded border border-line px-1.5 font-mono text-[0.75rem] tabular-nums text-muted">
      {stars.toLocaleString("en-US")}
    </span>
  );
}
