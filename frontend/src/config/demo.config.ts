/**
 * The no-signup landing-page demo. Fully isolated from the real
 * pipeline: it always runs the bundled simulator, never the backend,
 * regardless of API mode — exactly like the production demo system
 * will be. Toggle visibility via appConfig.features.demo.
 */

import { Swords, TrendingUp, Users, type LucideIcon } from "lucide-react";

export interface DemoBrief {
  label: string;
  brief: string;
}

export const DEMO_BRIEFS: DemoBrief[] = [
  {
    label: "UK market entry — DTC skincare",
    brief:
      "Client is a US-based DTC skincare brand (~$6M ARR) considering UK expansion in Q4. Need: market size and structure, regulatory requirements post-Brexit, recent comparable entrants and how they performed, and a go/no-go recommendation with budget.",
  },
  {
    label: "Competitor teardown — vertical SaaS",
    brief:
      "Deep teardown of the two leading project-management tools for architecture studios, for a client building a competitor: feature matrix, pricing strategy, churn complaints, and the wedge.",
  },
  {
    label: "Investor memo — market benchmarks",
    brief:
      "Benchmark pricing and take rates across mid-tier creator monetization platforms for an investor memo, with sources for every figure.",
  },
];

/** Characters of the report shown before the sign-up fade. */
export const DEMO_REPORT_PREVIEW_CHARS = 1400;

/** Suggestion cards under the workspace composer: an icon + short label + a
 *  one-line hint; clicking drops the full `brief` into the composer. */
export interface WorkspaceExample {
  icon: LucideIcon;
  label: string;
  hint: string;
  brief: string;
}

export const WORKSPACE_EXAMPLES: WorkspaceExample[] = [
  {
    icon: TrendingUp,
    label: "Market entry analysis",
    hint: "Regulation, structure, a go/no-go call",
    brief:
      "Market entry analysis: my client (US DTC skincare, ~$6M ARR) wants to expand to the UK in Q4. Regulatory path, market structure, recent comparable entrants, go/no-go with budget.",
  },
  {
    icon: Swords,
    label: "Competitor teardown",
    hint: "Features, pricing, and the wedge",
    brief:
      "Competitor teardown of Notion, Coda, and Slite for a client positioning a docs tool for law firms.",
  },
  {
    icon: Users,
    label: "Source & profile leads",
    hint: "Find, vet, and brief on prospects",
    brief:
      "Find and profile the 10 most active angel investors in climate-tech seed rounds in Europe this year.",
  },
];
