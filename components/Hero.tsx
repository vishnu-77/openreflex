import { GithubIcon } from "./GithubIcon";
import { LINKS } from "@/lib/site";
import { CopyButton } from "./CopyButton";
import { GithubStars } from "./GithubStars";
import { ReflexReplay } from "./ReflexReplay";
import { ResearchLink } from "./ViewToggle";

const INSTALL = "pipx install openreflex";

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden border-b border-line">
      <div className="grid-backdrop pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-[1320px] items-center gap-14 px-5 pb-20 pt-16 sm:px-10 sm:pt-24 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)] lg:gap-16 lg:pb-28">
        <div className="max-w-[40rem]">
          <p className="font-mono text-[0.8rem] text-accent">Open source, MIT licensed, runs on your machine</p>
          <h1 className="mt-5 font-serif text-[2.9rem] leading-[0.98] tracking-[-0.02em] text-ink sm:text-[4.1rem]">
            Muscle memory for AI&nbsp;coding agents.
          </h1>
          <p className="mt-7 max-w-[36rem] text-[1.08rem] leading-[1.7] text-muted">
            AI coding agents often solve the task, but not efficiently: they search the same code again, reread files,
            retry failed commands and keep going after the evidence is in. OpenReflex learns how each task gets done,
            recommends a more efficient path for the next one, and tells the agent when to continue, pivot or stop.
            Everything stays on your machine.
          </p>

          <div className="mt-9 flex max-w-[26rem] items-center gap-3 rounded-lg bg-term py-2 pl-4 pr-2 font-mono text-[0.9rem] text-term-text">
            <span className="select-none text-term-dim">$</span>
            <code className="flex-1 truncate">{INSTALL}</code>
            <CopyButton text={INSTALL} label="Copy install command" />
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <a
              href="#quickstart"
              className="inline-flex h-11 items-center rounded-md bg-ink px-5 text-[0.95rem] font-medium text-bg transition-transform hover:-translate-y-0.5"
            >
              Set up your agent
            </a>
            <a
              href={LINKS.github}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-11 items-center gap-2 rounded-md border border-line-strong px-5 text-[0.95rem] text-ink transition-colors hover:bg-panel"
            >
              <GithubIcon size={16} />
              View on GitHub
              <GithubStars />
            </a>
          </div>
          <p className="view-builder mt-6 text-[0.95rem] text-muted">
            Evaluating the approach? <ResearchLink />
          </p>
          <p className="view-research mt-6 text-[0.95rem] text-muted">
            You are in the Researcher view: how OpenReflex learns, and where it fits among related work.
          </p>
        </div>

        <ReflexReplay />
      </div>
    </section>
  );
}
