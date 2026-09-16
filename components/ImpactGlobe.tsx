import type { CSSProperties } from "react";
import type { GrowthStage, ImpactSnapshot } from "@/lib/impact";
import { SectionHeader } from "./SectionHeader";

const STAGES: GrowthStage[] = ["seed", "sprout", "sapling", "tree", "grove", "forest"];

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-GB").format(value);
}

function compact(value: number) {
  return new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function Tree({ x, y, scale = 1, mature = true }: { x: number; y: number; scale?: number; mature?: boolean }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <g className="impact-tree-enter">
        <path d="M0 0V-63" fill="none" stroke="var(--ink)" strokeWidth="7" strokeLinecap="round" />
        <path d="M0-42L-20-57M0-50L19-69M0-28L25-42" fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
        {mature ? (
          <g fill="var(--accent)">
            <circle cx="-24" cy="-70" r="24" />
            <circle cx="5" cy="-83" r="29" />
            <circle cx="31" cy="-64" r="22" />
            <circle cx="-3" cy="-55" r="26" />
          </g>
        ) : (
          <g fill="var(--accent)">
            <ellipse cx="-12" cy="-61" rx="14" ry="8" transform="rotate(-24 -12 -61)" />
            <ellipse cx="14" cy="-70" rx="14" ry="8" fill="var(--accent)" transform="rotate(24 14 -70)" />
          </g>
        )}
      </g>
    </g>
  );
}

function Ecosystem({ impact }: { impact: ImpactSnapshot }) {
  const rank = STAGES.indexOf(impact.stage);
  const growthBase = [0.12, 0.28, 0.5, 0.76, 0.9, 1][rank];
  const nextBase = [0.28, 0.5, 0.76, 0.9, 1, 1][rank];
  const growth = growthBase + (nextBase - growthBase) * impact.stageProgress;
  const forestPositions = [
    [122, 246, 0.52],
    [292, 249, 0.48],
    [96, 258, 0.36],
    [322, 260, 0.34],
    [151, 256, 0.3],
    [268, 258, 0.28],
    [77, 269, 0.24],
    [340, 271, 0.22],
    [182, 263, 0.22],
    [240, 264, 0.2],
    [110, 274, 0.18],
  ] as const;

  return (
    <div className="relative mx-auto w-full max-w-[520px]" aria-hidden="true">
      <svg viewBox="0 0 420 360" className="h-auto w-full overflow-visible">
        <defs>
          <clipPath id="impact-globe-clip">
            <circle cx="210" cy="170" r="138" />
          </clipPath>
        </defs>

        <circle cx="210" cy="170" r="138" fill="var(--bg-soft)" stroke="var(--border-strong)" strokeWidth="1.5" />
        <g fill="none" stroke="var(--border)" strokeWidth="1" opacity="0.8">
          <ellipse cx="210" cy="170" rx="138" ry="50" />
          <ellipse cx="210" cy="170" rx="138" ry="94" />
          <ellipse cx="210" cy="170" rx="54" ry="138" />
          <ellipse cx="210" cy="170" rx="101" ry="138" />
        </g>

        <g clipPath="url(#impact-globe-clip)">
          {Array.from({ length: impact.rain.drops }, (_, index) => {
            const x = 88 + ((index * 47) % 244);
            const y = 40 + ((index * 31) % 90);
            const style: CSSProperties = { animationDelay: `${-(index % 8) * 0.23}s` };
            return (
              <path
                key={`${x}-${y}-${index}`}
                d={`M${x} ${y}l-4 12`}
                className="impact-rain-drop"
                style={style}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="2"
                strokeLinecap="round"
                opacity="0.46"
              />
            );
          })}

          <path d="M53 250Q128 218 210 235Q287 207 367 249V330H53Z" fill="var(--muted-bg)" />
          <path d="M53 250Q128 218 210 235Q287 207 367 249" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" />

          {rank >= 4 &&
            forestPositions.slice(0, Math.max(0, impact.forestTrees - 1)).map(([x, y, scale], index) => (
              <Tree key={`${x}-${y}`} x={x} y={y} scale={scale} mature={rank >= 5 || index % 2 === 0} />
            ))}

          {rank === 0 ? (
            <g className="impact-seed-enter">
              <ellipse cx="210" cy="239" rx="13" ry="7" fill="var(--signal)" transform="rotate(-18 210 239)" />
              {impact.stageProgress > 0.45 && (
                <path d="M210 236Q207 224 214 218" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
              )}
            </g>
          ) : (
            <g
              style={{ transform: `translateY(${(1 - growth) * 31}px) scale(${0.58 + growth * 0.42})`, transformOrigin: "210px 244px" }}
              className="impact-tree-grow"
            >
              {rank === 1 ? (
                <g>
                  <path d="M210 243Q210 219 211 197" fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
                  <ellipse cx="196" cy="207" rx="16" ry="9" fill="var(--accent)" transform="rotate(-28 196 207)" />
                  <ellipse cx="225" cy="195" rx="17" ry="9" fill="var(--accent)" transform="rotate(28 225 195)" />
                </g>
              ) : (
                <Tree x={210} y={245} scale={rank === 2 ? 0.72 : 1.08} mature={rank >= 3} />
              )}
            </g>
          )}
        </g>

        <circle cx="210" cy="170" r="138" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        <circle cx="210" cy="170" r="146" fill="none" stroke="var(--border)" strokeWidth="1" strokeDasharray="2 7" />
      </svg>

      <div className="mt-2 flex items-center justify-center gap-2 font-mono text-[0.7rem] uppercase tracking-[0.12em] text-muted">
        <span>{impact.stage}</span>
        <span aria-hidden="true">/</span>
        <span>{Math.round(impact.stageProgress * 100)}% to next stage</span>
      </div>
    </div>
  );
}

export function ImpactGlobe({ impact }: { impact: ImpactSnapshot }) {
  const currentRank = STAGES.indexOf(impact.stage);

  return (
    <section id="impact" aria-labelledby="impact-title" className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-20 sm:px-10 sm:py-28">
        <SectionHeader
          id="impact"
          title="Less inference, visible growth"
          intro="A website-only view of avoided inference. As the aggregate token counter rises, rain falls inside the globe and one seed grows into a forest."
        />

        <div className="mt-12 grid items-center gap-14 lg:grid-cols-[minmax(0,1.05fr)_minmax(340px,0.95fr)] lg:gap-20">
          <Ecosystem impact={impact} />

          <div>
            <p className="font-mono text-[0.76rem] uppercase tracking-[0.14em] text-accent">OpenReflex / impact</p>
            <p className="mt-3 font-serif text-[2.6rem] leading-none tracking-[-0.025em] text-ink sm:text-[3.5rem]">
              {formatNumber(impact.tokensSaved)}
            </p>
            <p className="mt-2 text-[1rem] text-muted">aggregate tokens avoided</p>

            <div className="mt-8 grid grid-cols-2 border-y border-line sm:grid-cols-3">
              <div className="py-5 pr-5">
                <p className="font-mono text-[0.72rem] uppercase tracking-[0.1em] text-muted">Growth</p>
                <p className="mt-2 text-[1.05rem] font-medium capitalize text-ink">{impact.stage}</p>
              </div>
              <div className="border-l border-line px-5 py-5">
                <p className="font-mono text-[0.72rem] uppercase tracking-[0.1em] text-muted">Rain unit</p>
                <p className="mt-2 text-[1.05rem] font-medium text-ink">{compact(impact.rain.tokensPerDrop)} tokens</p>
              </div>
              <div className="col-span-2 border-t border-line py-5 sm:col-span-1 sm:border-l sm:border-t-0 sm:pl-5">
                <p className="font-mono text-[0.72rem] uppercase tracking-[0.1em] text-muted">Visual trees</p>
                <p className="mt-2 text-[1.05rem] font-medium text-ink">{impact.forestTrees}</p>
              </div>
            </div>

            {impact.environmental ? (
              <div className="mt-7 border-l-2 border-accent pl-5">
                <p className="font-mono text-[0.72rem] uppercase tracking-[0.1em] text-accent">Estimated environmental equivalent</p>
                <p className="mt-2 text-[1.2rem] font-medium text-ink">
                  {impact.environmental.treeDays.toFixed(2)} EPA urban-tree-equivalent days
                </p>
                <p className="mt-1 text-[0.92rem] leading-6 text-muted">
                  From {impact.environmental.co2eKg.toFixed(3)} kg CO₂e supplied by the impact data source. This is a
                  communication equivalence using the EPA urban-tree assumption, not a claim that trees were planted,
                  protected or physically saved.
                </p>
              </div>
            ) : (
              <p className="mt-7 max-w-[35rem] text-[0.92rem] leading-6 text-muted">
                The tree grows from token efficiency alone. A carbon/tree equivalence stays hidden until the website is
                given a defensible CO₂e estimate; OpenReflex does not invent a universal CO₂-per-token number.
              </p>
            )}

            <div className="mt-8 flex flex-wrap gap-x-4 gap-y-2 border-t border-line pt-5 font-mono text-[0.7rem] uppercase tracking-[0.08em] text-muted">
              {STAGES.map((stage, index) => (
                <span key={stage} className={index <= currentRank ? "text-accent" : undefined}>
                  {stage}
                </span>
              ))}
            </div>

            <p className="mt-5 text-[0.78rem] leading-5 text-muted">
              Source: {impact.sourceLabel}
              {impact.updatedAt ? ` · updated ${impact.updatedAt}` : ""}. Rain is a visual scale: one rendered drop represents
              approximately {compact(impact.rain.tokensPerDrop)} avoided tokens.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
