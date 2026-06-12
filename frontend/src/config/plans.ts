/**
 * Subscription plans — single source of truth for the pricing page,
 * settings/billing, and memory tier gating.
 */

export type PlanId = "free" | "starter" | "pro" | "agency";
export type MemoryTier = "episodic" | "wiki" | "semantic" | "procedural";

export interface Plan {
  id: PlanId;
  name: string;
  monthlyUsd: number;
  tokenBudget: number;
  tagline: string;
  memoryTiers: MemoryTier[];
  features: string[];
  highlight?: boolean;
}

export const PLANS: Plan[] = [
  {
    id: "free",
    name: "Seedling",
    monthlyUsd: 0,
    tokenBudget: 100_000,
    tagline: "Feel the continuity. Three real runs a month.",
    memoryTiers: ["episodic"],
    features: [
      "100k tokens / month",
      // "Episodic memory — Clannon remembers every run",
      "Single research workflow",
      "Community support",
    ],
  },
  {
    id: "starter",
    name: "Starter",
    monthlyUsd: 29,
    tokenBudget: 2_000_000,
    tagline: "For the freelancer with recurring clients.",
    memoryTiers: ["episodic", "wiki"],
    features: [
      "2M tokens / month",
      "Episodic + Wiki memory",
      "Editable client wiki — your facts outrank inference",
      "All research workflows",
      "Email delivery",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    monthlyUsd: 79,
    tokenBudget: 6_000_000,
    tagline: "The full memory system. This is where it compounds.",
    memoryTiers: ["episodic", "wiki", "semantic", "procedural"],
    features: [
      "6M tokens / month",
      "All four memory tiers",
      "Semantic graph — facts, sources, provenance",
      "Procedural memory — it learns how you work",
      "Per-layer model configuration",
      "Priority queue",
    ],
    highlight: true,
  },
  {
    id: "agency",
    name: "Agency",
    monthlyUsd: 199,
    tokenBudget: 20_000_000,
    tagline: "Every client, every project, one growing archive.",
    memoryTiers: ["episodic", "wiki", "semantic", "procedural"],
    features: [
      "20M tokens / month",
      "All four memory tiers",
      "Unlimited client workspaces",
      "MCP integrations — context flows in automatically",
      "Team seats (up to 5)",
      "Dedicated support",
    ],
  },
];

export const TIER_LABELS: Record<MemoryTier, string> = {
  episodic: "Episodic",
  wiki: "Wiki",
  semantic: "Semantic",
  procedural: "Procedural",
};

export function planById(id: PlanId): Plan {
  return PLANS.find((p) => p.id === id) ?? PLANS[0];
}
