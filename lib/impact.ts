export type GrowthStage = "seed" | "sprout" | "sapling" | "tree" | "grove" | "forest";

export type ImpactSnapshot = {
  tokensSaved: number;
  stage: GrowthStage;
  stageProgress: number;
  rain: {
    drops: number;
    tokensPerDrop: number;
  };
  forestTrees: number;
  environmental: null | {
    co2eKg: number;
    treeDays: number;
    methodology: string;
  };
  sourceLabel: string;
  updatedAt: string | null;
};

const EPA_TREE_KG_CO2_PER_YEAR = 60;

const STAGES: Array<{ stage: GrowthStage; from: number; to: number }> = [
  { stage: "seed", from: 0, to: 25_000 },
  { stage: "sprout", from: 25_000, to: 250_000 },
  { stage: "sapling", from: 250_000, to: 1_000_000 },
  { stage: "tree", from: 1_000_000, to: 5_000_000 },
  { stage: "grove", from: 5_000_000, to: 25_000_000 },
  { stage: "forest", from: 25_000_000, to: Number.POSITIVE_INFINITY },
];

function nonNegativeNumber(value: string | undefined): number | null {
  if (!value?.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function growth(tokensSaved: number): { stage: GrowthStage; progress: number } {
  const current = STAGES.find((entry) => tokensSaved < entry.to) ?? STAGES[STAGES.length - 1];
  if (!Number.isFinite(current.to)) {
    const extraOrders = Math.max(0, Math.log10(Math.max(tokensSaved, current.from)) - Math.log10(current.from));
    return { stage: current.stage, progress: Math.min(1, 0.65 + extraOrders * 0.12) };
  }
  return {
    stage: current.stage,
    progress: Math.max(0, Math.min(1, (tokensSaved - current.from) / (current.to - current.from))),
  };
}

function rainScale(tokensSaved: number): { drops: number; tokensPerDrop: number } {
  if (tokensSaved <= 0) return { drops: 0, tokensPerDrop: 1_000 };
  const tokensPerDrop =
    tokensSaved < 100_000 ? 5_000 : tokensSaved < 1_000_000 ? 25_000 : tokensSaved < 25_000_000 ? 250_000 : 1_000_000;
  return {
    drops: Math.max(3, Math.min(24, Math.ceil(tokensSaved / tokensPerDrop))),
    tokensPerDrop,
  };
}

function treeCount(stage: GrowthStage, progress: number): number {
  if (stage === "forest") return 7 + Math.round(progress * 5);
  if (stage === "grove") return 3 + Math.round(progress * 3);
  if (stage === "tree") return 1;
  return 0;
}

/**
 * Website-only aggregate impact snapshot.
 *
 * The site remains a static Next.js export, so this executes at build time. A deployment can supply aggregate
 * values without introducing runtime telemetry into OpenReflex itself:
 *
 *   OPENREFLEX_TOKENS_SAVED=18400000
 *   OPENREFLEX_CO2E_KG=2.31
 *   OPENREFLEX_IMPACT_SOURCE="opt-in aggregate"
 *   OPENREFLEX_IMPACT_UPDATED_AT="2026-09-15T14:00:00Z"
 *
 * CO2e is intentionally not inferred from token count here: model, hardware, batching and electricity mix matter.
 * When a defensible upstream estimate is supplied, we convert it to EPA urban-tree sequestration-equivalent days.
 */
export function getImpactSnapshot(): ImpactSnapshot {
  const tokensSaved = Math.floor(nonNegativeNumber(process.env.OPENREFLEX_TOKENS_SAVED) ?? 0);
  const co2eKg = nonNegativeNumber(process.env.OPENREFLEX_CO2E_KG);
  const { stage, progress } = growth(tokensSaved);

  return {
    tokensSaved,
    stage,
    stageProgress: Number(progress.toFixed(4)),
    rain: rainScale(tokensSaved),
    forestTrees: treeCount(stage, progress),
    environmental:
      co2eKg === null
        ? null
        : {
            co2eKg,
            treeDays: Number(((co2eKg * 365) / EPA_TREE_KG_CO2_PER_YEAR).toFixed(4)),
            methodology: "supplied CO2e estimate + EPA 60 kg CO2/tree/year equivalence",
          },
    sourceLabel: process.env.OPENREFLEX_IMPACT_SOURCE?.trim() || "website aggregate",
    updatedAt: process.env.OPENREFLEX_IMPACT_UPDATED_AT?.trim() || null,
  };
}
