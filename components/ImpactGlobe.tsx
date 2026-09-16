import type { CSSProperties } from "react";
import type { GrowthStage, ImpactSnapshot } from "@/lib/impact";

const STAGES: GrowthStage[] = ["seed", "sprout", "sapling", "tree", "grove", "forest"];

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-GB").format(value);
}

function compact(value: number) {
  return new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

type TreeProps = {
  x: number;
  y: number;
  scale?: number;
  delay?: number;
  young?: boolean;
  muted?: boolean;
};

function Tree({ x, y, scale = 1, delay = 0, young = false, muted = false }: TreeProps) {
  const style = { animationDelay: `${delay}s` } as CSSProperties;
  const canopy = muted ? "var(--border-strong)" : "var(--accent)";
  const canopySoft = muted ? "var(--border)" : "var(--accent-strong)";

  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <g className="impact-tree-rise" style={style}>
        <path
          d={young ? "M0 0 C-1 -27 2 -47 1 -69" : "M0 0 C-6 -31 -1 -63 0 -103 C2 -126 -3 -151 4 -174"}
          fill="none"
          stroke="var(--ink)"
          strokeWidth={young ? 7 : 11}
          strokeLinecap="round"
        />
        {!young && (
          <g fill="none" stroke="var(--ink)" strokeWidth="6" strokeLinecap="round">
            <path d="M-1-83C-22-99-33-115-45-131" />
            <path d="M1-103C24-119 35-137 48-151" />
            <path d="M1-126C-17-141-24-157-31-169" />
          </g>
        )}

        <g className="impact-canopy-sway" style={style}>
          {young ? (
            <>
              <path d="M1-64C-20-81-36-72-36-58C-35-47-17-48 1-56Z" fill={canopy} />
              <path d="M1-70C18-86 37-79 39-64C40-51 21-49 1-60Z" fill={canopySoft} />
            </>
          ) : (
            <>
              <path
                d="M-64-132C-78-163-57-191-28-192C-14-218 24-221 41-196C74-196 92-164 76-137C89-111 68-85 38-89C17-70-19-75-30-98C-55-94-76-108-64-132Z"
                fill={canopy}
              />
              <path
                d="M-49-154C-53-179-34-197-12-194C2-211 28-206 34-187C55-184 63-160 49-145C58-123 40-109 22-114C9-103-13-105-23-119C-38-116-53-132-49-154Z"
                fill={canopySoft}
                opacity="0.82"
              />
              <path
                d="M-26-185C-20-202-3-211 12-202C25-212 43-202 43-186C56-176 50-157 35-153C26-140 4-143-2-154C-18-153-31-168-26-185Z"
                fill={canopy}
              />
            </>
          )}
        </g>
      </g>
    </g>
  );
}

function Grass({ x, y, delay }: { x: number; y: number; delay: number }) {
  const style = { animationDelay: `${delay}s` } as CSSProperties;
  return (
    <g transform={`translate(${x} ${y})`} className="impact-grass-sway" style={style} fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" opacity="0.55">
      <path d="M0 0Q-4-14-8-23M0 0Q2-17 8-27M0 0Q8-10 14-14" />
    </g>
  );
}

function Landscape({ impact }: { impact: ImpactSnapshot }) {
  const rank = STAGES.indexOf(impact.stage);
  const backgroundTrees = [
    [105, 405, 0.42],
    [176, 412, 0.36],
    [742, 410, 0.4],
    [808, 416, 0.34],
    [250, 430, 0.28],
    [674, 430, 0.27],
    [58, 438, 0.24],
    [852, 440, 0.23],
    [315, 438, 0.2],
    [602, 438, 0.2],
  ] as const;

  const visibleBackground = rank >= 5 ? 10 : rank >= 4 ? Math.max(3, impact.forestTrees + 1) : 0;
  const grass = Array.from({ length: 24 }, (_, index) => ({
    x: 20 + ((index * 73) % 860),
    y: 438 + ((index * 19) % 33),
    delay: -(index % 9) * 0.22,
  }));

  return (
    <div className="relative overflow-hidden border border-line-strong bg-bg-soft">
      <svg viewBox="0 0 900 520" className="block h-auto w-full" role="img" aria-label={`${impact.stage} stage OpenReflex impact landscape`}>
        <rect width="900" height="520" fill="var(--bg-soft)" />

        <g className="impact-cloud-drift impact-cloud-a" opacity="0.68">
          <path d="M82 116C87 91 111 79 132 91C142 64 181 61 193 90C221 82 242 101 240 124H82Z" fill="var(--muted-bg)" stroke="var(--border)" />
        </g>
        <g className="impact-cloud-drift impact-cloud-b" opacity="0.52">
          <path d="M618 88C624 67 645 57 663 67C675 43 707 43 720 67C744 60 766 77 765 98H618Z" fill="var(--muted-bg)" stroke="var(--border)" />
        </g>

        <g className="impact-wind-layer" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" strokeLinecap="round" opacity="0.6">
          <path d="M55 183C127 160 202 164 260 181" />
          <path d="M574 154C655 132 744 141 824 166" />
          <path d="M111 231C198 211 267 220 328 241" />
        </g>

        {Array.from({ length: impact.rain.drops }, (_, index) => {
          const x = 28 + ((index * 101) % 842);
          const y = 45 + ((index * 37) % 165);
          const style = { animationDelay: `${-(index % 10) * 0.18}s` } as CSSProperties;
          return (
            <path
              key={`${x}-${y}-${index}`}
              d={`M${x} ${y}l-7 21`}
              className="impact-rain-drop"
              style={style}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="1.8"
              strokeLinecap="round"
              opacity="0.34"
            />
          );
        })}

        <path d="M0 350C116 315 225 322 338 353C446 381 573 356 900 304V520H0Z" fill="var(--muted-bg)" />
        <path d="M0 395C168 354 304 386 425 413C584 448 714 394 900 368V520H0Z" fill="var(--bg)" />
        <path d="M0 350C116 315 225 322 338 353C446 381 573 356 900 304" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" />
        <path d="M0 395C168 354 304 386 425 413C584 448 714 394 900 368" fill="none" stroke="var(--border)" strokeWidth="1.5" />

        {backgroundTrees.slice(0, visibleBackground).map(([x, y, scale], index) => (
          <Tree key={`${x}-${y}`} x={x} y={y} scale={scale} delay={-(index % 5) * 0.35} muted />
        ))}

        {rank === 0 && (
          <g className="impact-seed-enter">
            <ellipse cx="452" cy="425" rx="14" ry="8" fill="var(--signal)" transform="rotate(-18 452 425)" />
            {impact.stageProgress > 0.45 && <path d="M451 421Q447 401 456 389" fill="none" stroke="var(--accent)" strokeWidth="4" strokeLinecap="round" />}
          </g>
        )}

        {rank === 1 && <Tree x={451} y={432} scale={0.72} young delay={-0.3} />}
        {rank === 2 && <Tree x={451} y={437} scale={0.72} delay={-0.4} />}
        {rank >= 3 && <Tree x={451} y={442} scale={1.08} delay={-0.5} />}

        {rank >= 4 && (
          <>
            <Tree x={335} y={449} scale={0.68} delay={-1.1} />
            <Tree x={573} y={450} scale={0.64} delay={-1.6} />
          </>
        )}

        {rank >= 5 && (
          <>
            <Tree x={251} y={455} scale={0.54} delay={-2.1} />
            <Tree x={662} y={457} scale={0.5} delay={-2.6} />
          </>
        )}

        {grass.map((blade) => (
          <Grass key={`${blade.x}-${blade.y}`} {...blade} />
        ))}

        <path d="M0 468C190 454 332 478 480 470C634 462 772 438 900 452" fill="none" stroke="var(--border-strong)" strokeWidth="1" opacity="0.7" />
      </svg>

      <div className="absolute bottom-4 left-4 border border-line bg-bg/90 px-3 py-2 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-muted backdrop-blur-sm">
        <span className="text-accent">{impact.stage}</span>
        <span className="mx-2">/</span>
        {Math.round(impact.stageProgress * 100)}% to next stage
      </div>
    </div>
  );
}

export function ImpactLandscape({ impact }: { impact: ImpactSnapshot }) {
  const currentRank = STAGES.indexOf(impact.stage);

  return (
    <div className="mx-auto max-w-[1320px] px-5 pb-20 pt-12 sm:px-10 sm:pb-28 sm:pt-16">
      <div className="grid gap-7 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)] lg:items-start lg:gap-8">
        <Landscape impact={impact} />

        <aside className="border border-line-strong bg-panel p-6 sm:p-7">
          <p className="font-mono text-[0.72rem] uppercase tracking-[0.14em] text-accent">Current aggregate</p>
          <p className="mt-4 font-serif text-[3.1rem] leading-none tracking-[-0.025em] text-ink sm:text-[4rem]">{formatNumber(impact.tokensSaved)}</p>
          <p className="mt-2 text-[0.98rem] text-muted">tokens avoided</p>

          <div className="mt-8 divide-y divide-line border-y border-line">
            <div className="flex items-center justify-between py-4">
              <span className="font-mono text-[0.72rem] uppercase tracking-[0.08em] text-muted">Growth stage</span>
              <span className="font-medium capitalize text-ink">{impact.stage}</span>
            </div>
            <div className="flex items-center justify-between py-4">
              <span className="font-mono text-[0.72rem] uppercase tracking-[0.08em] text-muted">Rain scale</span>
              <span className="font-medium text-ink">1 / {compact(impact.rain.tokensPerDrop)}</span>
            </div>
            <div className="flex items-center justify-between py-4">
              <span className="font-mono text-[0.72rem] uppercase tracking-[0.08em] text-muted">Visual trees</span>
              <span className="font-medium text-ink">{impact.forestTrees}</span>
            </div>
          </div>

          {impact.environmental ? (
            <div className="mt-7 border-l-2 border-accent pl-4">
              <p className="font-mono text-[0.7rem] uppercase tracking-[0.1em] text-accent">Environmental equivalent</p>
              <p className="mt-2 text-[1.08rem] font-medium leading-6 text-ink">{impact.environmental.treeDays.toFixed(2)} EPA urban-tree-equivalent days</p>
              <p className="mt-2 text-[0.84rem] leading-5 text-muted">
                Derived from {impact.environmental.co2eKg.toFixed(3)} kg CO₂e supplied by the impact data source. It is a communication equivalence, not a claim that physical trees were planted, protected or saved.
              </p>
            </div>
          ) : (
            <p className="mt-7 text-[0.86rem] leading-6 text-muted">
              The landscape grows from token efficiency alone. Carbon equivalence stays hidden until a defensible upstream CO₂e estimate is supplied.
            </p>
          )}

          <div className="mt-8 flex flex-wrap gap-x-3 gap-y-2 border-t border-line pt-5 font-mono text-[0.66rem] uppercase tracking-[0.08em] text-muted">
            {STAGES.map((stage, index) => (
              <span key={stage} className={index <= currentRank ? "text-accent" : undefined}>{stage}</span>
            ))}
          </div>
        </aside>
      </div>

      <div className="mt-7 grid gap-5 border-t border-line pt-6 text-[0.82rem] leading-5 text-muted sm:grid-cols-2">
        <p>
          Source: {impact.sourceLabel}{impact.updatedAt ? ` · updated ${impact.updatedAt}` : ""}. Rain is a visual scale; each rendered drop represents approximately {compact(impact.rain.tokensPerDrop)} avoided tokens.
        </p>
        <p>
          The scene is a visual metaphor for cumulative efficiency. Breeze, rain and growth are intentionally illustrative; only the displayed aggregate and supplied CO₂e value are quantitative.
        </p>
      </div>
    </div>
  );
}
