import type {
  DecisionKind,
  LayerModelConfig,
  MemoryEntry,
  Project,
  Run,
  Source,
  UsageSummary,
} from "./types";

/** Seed projects (clients / bodies of work). Runs + memory below are tagged to these. */
export const SEED_PROJECTS: Project[] = [
  { id: "proj_meridian", name: "Meridian Skincare", createdAt: new Date(Date.now() - 30 * 3_600_000).toISOString(), color: "moss" },
  { id: "proj_arch", name: "Studio PM teardown", createdAt: new Date(Date.now() - 49 * 3_600_000).toISOString(), color: "clay" },
  { id: "proj_creator", name: "Creator benchmarks", createdAt: new Date(Date.now() - 73 * 3_600_000).toISOString(), color: "indigo" },
];

/* ------------------------------------------------------------------
   Seeds and scripts for the mock simulator. Nothing in here is
   imported by pages — only by MockClient.
------------------------------------------------------------------- */

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

export const SEED_SOURCES: Source[] = [
  { id: "s1", title: "Statista — UK skincare market outlook 2026", url: "https://www.statista.com/outlook/cmo/beauty-personal-care/skin-care/united-kingdom", domain: "statista.com" },
  { id: "s2", title: "GOV.UK — Cosmetic products regulation guidance", url: "https://www.gov.uk/guidance/making-cosmetic-products-available-to-consumers", domain: "gov.uk" },
  { id: "s3", title: "Mintel — UK beauty retailing report", url: "https://store.mintel.com/report/uk-beauty-retailing-market-report", domain: "mintel.com" },
  { id: "s4", title: "The Industry.beauty — DTC margin benchmarks", url: "https://theindustry.beauty/dtc-margins-2026", domain: "theindustry.beauty" },
  { id: "s5", title: "Charlotte Tilbury case study — Retail Week", url: "https://www.retail-week.com/beauty/charlotte-tilbury-dtc", domain: "retail-week.com" },
  { id: "s6", title: "Ofcom — UK online behaviour survey", url: "https://www.ofcom.org.uk/research-and-data", domain: "ofcom.org.uk" },
];

export const SAMPLE_REPORT = `# UK market entry — DTC skincare

## Executive summary

The UK skincare market is projected to reach **£3.4B by end of 2026**, with online channels accounting for 38% of revenue and growing roughly 2.3× faster than retail [1]. For a US-based DTC brand, the UK remains the most attractive European entry point: shared language, mature parcel infrastructure, and a consumer base already conditioned to direct-to-consumer subscription models. The window, however, is narrowing — three comparable US brands entered in the last 18 months, and paid acquisition costs on Meta UK rose 31% year-over-year [4].

## Market structure

- **Premium mass is the contested middle.** Boots and Superdrug anchor the low end; clinical brands (The Ordinary, CeraVe) compress pricing below £15. The defensible band for a new DTC entrant sits at **£22–£38 per SKU** [3].
- **Subscription fatigue is real but overstated.** Churn on UK beauty subscriptions averages 9.4%/mo, yet replenishment-led models (vs. discovery boxes) hold churn under 6% [4].
- **Retail is a second act, not an entry.** Every successful US entrant since 2023 launched DTC-first and added Space NK or Sephora UK placement in year two [5].

## Regulatory path

UK cosmetics regulation diverged from the EU after Brexit. Key obligations:

1. Appoint a **UK Responsible Person** before first sale [2].
2. Notify products via the **SCPN portal** — not the EU CPNP [2].
3. Labelling must carry the UK RP address; stickering over EU labels is permitted but inspected [2].

Lead time from engagement to compliance is typically **6–9 weeks** with a specialist consultancy; budget £4–7k for a 12-SKU line.

## Competitive read

| Brand | Entered | Model | Est. UK revenue |
|---|---|---|---|
| Topicals | 2024 | DTC + Sephora UK | £8–11M |
| Geologie | 2025 | DTC only | £2–3M |
| Dieux | 2025 | DTC + Space NK | £4–6M |

None of the three has localized formulations or UK-specific hero SKUs — positioning copy is lifted from US campaigns. A entrant that leads with UK-water-hardness skincare claims (a verified consumer pain point in London and the Southeast [6]) would own an unclaimed angle.

## Recommendation

Enter Q4 2026, DTC-first, with a 6-SKU replenishment line priced £24–£34. Engage a UK Responsible Person by August. Lead creative with the hard-water angle; reserve retail conversations until £150k/mo run rate. Total cost to first sale: **£38–52k** including compliance, 3PL setup (recommend Huboo or James and James), and a £25k initial media test.

## Assumptions and limits

Revenue estimates for private competitors are triangulated from Companies House filings and SimilarWeb traffic, confidence ±35%. Tariff treatment assumes finished goods manufactured in the US; reformulation or EU contract manufacturing changes the duty math materially.
`;

export interface ScriptStep {
  delay: number;
  kind: "status" | "log" | "expert" | "sources" | "usage" | "message";
  status?: Run["status"];
  log?: { kind: DecisionKind; title: string; detail?: string; meta?: Record<string, string> };
  expert?: { id: string; name: string; domain: string; status: "spawned" | "working" | "summarizing" | "done"; summary?: string; toolCalls: number };
  sources?: Source[];
  tokensUsed?: number;
  /** The orchestrator talking to the user (streamed as message_delta). */
  message?: string;
}

/**
 * The live-run script. Timings are tuned so a full run plays in
 * ~35 seconds — long enough to feel real, short enough to hold
 * attention.
 */
export function buildRunScript(): ScriptStep[] {
  return [
    { delay: 400, kind: "status", status: "sanitizing" },
    { delay: 700, kind: "log", log: { kind: "observation", title: "Intake accepted", detail: "text/plain · 1.4 KB · rate window clear" } },
    { delay: 900, kind: "log", log: { kind: "observation", title: "Sanitizers passed", detail: "ClamAV clean · no secrets · no PII flags", meta: { workers: "text", threat: "none" } } },
    { delay: 500, kind: "status", status: "verifying" },
    { delay: 1100, kind: "log", log: { kind: "route", title: "Verifier cleared input", detail: "No injection patterns · handoff integrity OK · routed to orchestrator", meta: { verdict: "proceed" } } },
    { delay: 600, kind: "status", status: "orchestrating" },
    { delay: 900, kind: "log", log: { kind: "hydration", title: "Memory hydrated", detail: "2 wiki · 3 episodic · 1 procedural — 1.9k tokens injected", meta: { tiers: "wiki, episodic, procedural", budget: "1.9k / 4k" } } },
    { delay: 1300, kind: "log", log: { kind: "route", title: "Entropy routing", detail: "H = 1.38 over domain centroids — query spans market, regulatory, and competitive domains", meta: { entropy: "1.38", experts: "3" } } },
    { delay: 500, kind: "message", message: "This spans three areas — market, regulatory, and competitive — so I'll bring in a specialist for each and synthesise as they report back." },
    { delay: 500, kind: "log", log: { kind: "expert_spawn", title: "Spawned web.research → market", detail: "Scope: market size, channel mix, pricing bands" } },
    { delay: 250, kind: "expert", expert: { id: "e1", name: "web.research", domain: "Market", status: "spawned", toolCalls: 0 } },
    { delay: 400, kind: "log", log: { kind: "expert_spawn", title: "Spawned web.research → regulatory", detail: "Scope: UK cosmetics compliance, post-Brexit divergence" } },
    { delay: 250, kind: "expert", expert: { id: "e2", name: "web.research", domain: "Regulatory", status: "spawned", toolCalls: 0 } },
    { delay: 400, kind: "log", log: { kind: "expert_spawn", title: "Spawned web.research → competitive", detail: "Scope: recent US entrants, positioning, revenue signals" } },
    { delay: 250, kind: "expert", expert: { id: "e3", name: "web.research", domain: "Competitive", status: "spawned", toolCalls: 0 } },
    { delay: 800, kind: "expert", expert: { id: "e1", name: "web.research", domain: "Market", status: "working", toolCalls: 1 } },
    { delay: 300, kind: "log", log: { kind: "tool_call", title: "web_search — market expert", detail: "“UK skincare market size 2026 online share” · 8 results" } },
    { delay: 700, kind: "expert", expert: { id: "e2", name: "web.research", domain: "Regulatory", status: "working", toolCalls: 1 } },
    { delay: 300, kind: "log", log: { kind: "tool_call", title: "web_search — regulatory expert", detail: "“UK responsible person cosmetics SCPN notification” · 6 results" } },
    { delay: 900, kind: "expert", expert: { id: "e3", name: "web.research", domain: "Competitive", status: "working", toolCalls: 1 } },
    { delay: 400, kind: "log", log: { kind: "tool_call", title: "fetch_url — gov.uk", detail: "Cosmetic products guidance · re-entered sanitization · clean" } },
    { delay: 1500, kind: "log", log: { kind: "tool_call", title: "fetch_url — statista.com", detail: "Market outlook tables extracted · 12 data points" } },
    { delay: 1100, kind: "expert", expert: { id: "e1", name: "web.research", domain: "Market", status: "working", toolCalls: 3 } },
    { delay: 1200, kind: "log", log: { kind: "observation", title: "Cross-check triggered", detail: "Market-size figures conflict (£3.1B vs £3.4B) — verifying against newer source", meta: { action: "recency-check" } } },
    { delay: 1600, kind: "expert", expert: { id: "e2", name: "web.research", domain: "Regulatory", status: "summarizing", toolCalls: 3 } },
    { delay: 1000, kind: "log", log: { kind: "observation", title: "Regulatory expert returned", detail: "Summary: 6-step compliance path, 6–9 week lead time. Full findings → output pipeline", meta: { summaryTokens: "210" } } },
    { delay: 400, kind: "expert", expert: { id: "e2", name: "web.research", domain: "Regulatory", status: "done", summary: "UK RP + SCPN notification required before first sale; 6–9 weeks, £4–7k for 12 SKUs.", toolCalls: 3 } },
    { delay: 1700, kind: "expert", expert: { id: "e1", name: "web.research", domain: "Market", status: "summarizing", toolCalls: 4 } },
    { delay: 900, kind: "log", log: { kind: "observation", title: "Market expert returned", detail: "Summary: £3.4B by 2026, online 38% and compounding. Full findings → output pipeline", meta: { summaryTokens: "188" } } },
    { delay: 300, kind: "expert", expert: { id: "e1", name: "web.research", domain: "Market", status: "done", summary: "£3.4B market by 2026; defensible DTC price band £22–£38; subscription churn manageable on replenishment models.", toolCalls: 4 } },
    { delay: 1500, kind: "expert", expert: { id: "e3", name: "web.research", domain: "Competitive", status: "summarizing", toolCalls: 5 } },
    { delay: 800, kind: "log", log: { kind: "observation", title: "Competitive expert returned", detail: "Summary: 3 recent US entrants, none localized. Full findings → output pipeline", meta: { summaryTokens: "204" } } },
    { delay: 300, kind: "expert", expert: { id: "e3", name: "web.research", domain: "Competitive", status: "done", summary: "Topicals, Geologie, Dieux entered since 2024 — all run US creative unchanged. Hard-water positioning is unclaimed.", toolCalls: 5 } },
    { delay: 600, kind: "sources", sources: SEED_SOURCES },
    { delay: 900, kind: "log", log: { kind: "route", title: "Synthesis started", detail: "synthesis.writer assembling draft from 3 expert findings + hydrated context" } },
    { delay: 2400, kind: "usage", tokensUsed: 248_000 },
    { delay: 1500, kind: "log", log: { kind: "answer", title: "Draft assembled", detail: "1,900 words · 6 sources cited · handing to output filter" } },
    { delay: 500, kind: "status", status: "filtering" },
    { delay: 1300, kind: "log", log: { kind: "observation", title: "Output filter", detail: "Citation integrity ✓ · groundedness ✓ · PII scan ✓ · schema ✓", meta: { verdict: "pass" } } },
    { delay: 400, kind: "usage", tokensUsed: 312_000 },
  ];
}

/**
 * Rebuilds the decision log a finished run would have left behind,
 * with timestamps spread from the run's start time.
 */
function buildSeedLog(startIso: string): Run["decisionLog"] {
  let t = new Date(startIso).getTime();
  let i = 0;
  const entries: Run["decisionLog"] = [];
  for (const step of buildRunScript()) {
    t += step.delay;
    if (step.kind !== "log") continue;
    entries.push({
      id: `seedlog_${startIso}_${++i}`,
      ts: new Date(t).toISOString(),
      ...step.log!,
    });
  }
  return entries;
}

export const SEED_RUNS: Run[] = [
  {
    id: "run_seed_1",
    projectId: "proj_meridian",
    title: "UK market entry — DTC skincare brand",
    brief:
      "Client is a US-based DTC skincare brand (~$6M ARR) considering UK expansion in Q4. Need: market size and structure, regulatory requirements post-Brexit, recent comparable entrants and how they performed, and a go/no-go recommendation with budget.",
    status: "delivered",
    createdAt: hoursAgo(26),
    tokensUsed: 312_000,
    expertCount: 3,
    decisionLog: buildSeedLog(hoursAgo(26)),
    experts: [
      { id: "e1", name: "web.research", domain: "Market", status: "done", summary: "£3.4B market by 2026; defensible DTC price band £22–£38.", toolCalls: 4 },
      { id: "e2", name: "web.research", domain: "Regulatory", status: "done", summary: "UK RP + SCPN notification required; 6–9 weeks lead time.", toolCalls: 3 },
      { id: "e3", name: "web.research", domain: "Competitive", status: "done", summary: "Three US entrants since 2024, none localized.", toolCalls: 5 },
    ],
    message:
      "Here's the UK entry analysis. Three specialists covered market, regulatory, and competitive in parallel — I flagged where the market-size figures disagreed and went with the newer source. The regulatory path is the main gating item, so the budget table sits up top of the report.",
    report: SAMPLE_REPORT,
    sources: SEED_SOURCES,
    inputs: [{ name: "meridian-financials.csv", modality: "text", size: 48_120 }],
    artifacts: [
      { id: "a1", run_id: "run_seed_1", name: "uk-market-entry.md", mime: "text/markdown", size: 11_240 },
      { id: "a2", run_id: "run_seed_1", name: "competitor-revenue.csv", mime: "text/csv", size: 2_980 },
    ],
  },
  {
    id: "run_seed_2",
    projectId: "proj_arch",
    title: "Competitor teardown — PM software for architects",
    brief: "Deep teardown of Monograph and Programa for a client building vertical PM software for architecture studios.",
    status: "delivered",
    createdAt: hoursAgo(49),
    tokensUsed: 287_000,
    expertCount: 2,
    decisionLog: buildSeedLog(hoursAgo(49)),
    experts: [
      { id: "e1", name: "web.research", domain: "Product", status: "done", summary: "Feature matrix across 11 dimensions; Monograph weak on phase-based billing.", toolCalls: 6 },
      { id: "e2", name: "web.research", domain: "Pricing", status: "done", summary: "Both anchor at $45–55/seat; annual-only contracts driving churn complaints.", toolCalls: 4 },
    ],
    report: "# Competitor teardown — PM software for architects\n\n## Summary\n\nMonograph and Programa both anchor pricing at $45–55 per seat but leave **phase-based billing** — the way architecture studios actually invoice — underserved. Full matrix and sourcing below.\n\n## Where they are strong\n\n- Monograph: time-tracking UX, US brand recognition among AIA firms\n- Programa: spec/FF&E workflows, strong in interior design crossover\n\n## The opening\n\nNeither product models **RIBA/AIA phase fee structures** natively; both communities surface this in reviews repeatedly. A studio-shaped billing engine is the wedge.\n",
    sources: SEED_SOURCES.slice(0, 3),
    inputs: [],
    artifacts: [],
  },
  {
    id: "run_seed_3",
    projectId: "proj_creator",
    title: "Creator-economy pricing benchmarks",
    brief: "Benchmark pricing for mid-tier creator monetization platforms for an investor memo.",
    status: "blocked",
    createdAt: hoursAgo(73),
    tokensUsed: 0,
    expertCount: 0,
    decisionLog: [
      {
        id: "seedlog_blocked_1",
        ts: hoursAgo(73),
        kind: "observation",
        title: "Intake accepted",
        detail: "text/plain · 18.2 KB · rate window clear",
      },
      {
        id: "seedlog_blocked_2",
        ts: hoursAgo(73),
        kind: "warning",
        title: "Sanitizer flag — PII",
        detail: "Pasted spreadsheet contains 240+ unredacted email addresses",
        meta: { worker: "text", threat: "high" },
      },
      {
        id: "seedlog_blocked_3",
        ts: hoursAgo(73),
        kind: "error",
        title: "Verifier blocked the run",
        detail: "Personal data cannot enter the research pipeline. Redact the sheet and resubmit — no tokens were charged for model work.",
        meta: { verdict: "block", reason: "pii_exposure" },
      },
    ],
    experts: [],
    report: undefined,
    sources: [],
    inputs: [],
    artifacts: [],
  },
];

export const SEED_MEMORY: MemoryEntry[] = [
  {
    id: "m1",
    projectId: "proj_meridian",
    tier: "wiki",
    title: "Client: Meridian Skincare — context",
    content:
      "US-based DTC skincare, ~$6M ARR, founder-led. Hero SKU is a ceramide serum. Brand voice: clinical but warm, never 'clean beauty' framing. Decision-maker: Priya (CMO). Always include a budget table in recommendations.",
    updatedAt: hoursAgo(30),
  },
  {
    id: "m2",
    projectId: "proj_meridian",
    tier: "wiki",
    title: "Research style guide",
    content:
      "Reports lead with an executive summary ≤120 words. Cite primary sources over aggregators. Flag any figure older than 18 months. British English for UK-market deliverables.",
    updatedAt: hoursAgo(120),
  },
  {
    id: "m3",
    projectId: "proj_meridian",
    tier: "semantic",
    title: "UK cosmetics rules diverged from EU CPNP",
    content: "Post-Brexit, UK requires SCPN notification and a UK Responsible Person — EU CPNP registration is not valid.",
    updatedAt: hoursAgo(26),
    confidence: 0.96,
    source: "gov.uk",
  },
  {
    id: "m4",
    projectId: "proj_meridian",
    tier: "semantic",
    title: "Meridian's defensible UK price band is £22–£38",
    content: "Derived from market-structure analysis: clinical brands compress below £15, premium mass contested at £22–£38.",
    updatedAt: hoursAgo(26),
    confidence: 0.81,
    source: "run_seed_1",
  },
  {
    id: "m5",
    projectId: "proj_meridian",
    tier: "episodic",
    title: "Delivered: UK market entry report",
    content: "3 experts, 312k tokens, 6 sources. Client accepted recommendation; follow-up on 3PL selection expected.",
    updatedAt: hoursAgo(26),
    runId: "run_seed_1",
  },
  {
    id: "m6",
    projectId: "proj_creator",
    tier: "episodic",
    title: "Blocked: creator-economy benchmarks",
    content: "Run blocked at verifier — brief contained a pasted spreadsheet with unredacted emails. User notified, resubmission pending.",
    updatedAt: hoursAgo(73),
    runId: "run_seed_3",
  },
  {
    id: "m7",
    projectId: "proj_meridian",
    tier: "procedural",
    title: "Market-entry briefs get a regulatory section",
    content: "Learned across 4 runs: when the brief involves selling into a new country, always spawn a regulatory expert even if not asked.",
    updatedAt: hoursAgo(50),
  },
  {
    id: "m8",
    projectId: "proj_arch",
    tier: "procedural",
    title: "Competitor tables sorted by estimated revenue",
    content: "User reorders tables this way when exporting — do it by default.",
    updatedAt: hoursAgo(90),
  },
];

export function buildSeedUsage(): UsageSummary {
  const days = 14;
  const byDay = Array.from({ length: days }, (_, i) => {
    const date = new Date(Date.now() - (days - 1 - i) * 86_400_000);
    // deterministic pseudo-random daily spend
    const seed = (i * 2654435761) % 97;
    return {
      date: date.toISOString().slice(0, 10),
      tokens: 60_000 + seed * 3_100,
    };
  });
  const used = byDay.reduce((a, d) => a + d.tokens, 0);
  return {
    periodStart: byDay[0].date,
    periodEnd: new Date(new Date(byDay[0].date).getTime() + 30 * 86_400_000)
      .toISOString()
      .slice(0, 10),
    budget: 6_000_000,
    used,
    byDay,
  };
}

/** Mirrors the backend MODEL_CATALOG (verified June 2026). */
const SELECTABLE_MODELS = [
  "gemini-3.5-flash",
  "gemini-3.1-pro-preview",
  "gemini-3.1-flash-lite",
  "gemini-2.5-pro",
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "claude-fable-5",
  "claude-opus-4-8",
  "claude-opus-4-7",
  "claude-opus-4-6",
  "claude-sonnet-4-6",
  "claude-haiku-4-5",
  "gpt-5.5",
  "gpt-5.4",
  "gpt-5.4-mini",
  "gpt-5.4-nano",
];

/** Vision-capable subset — the only models the media role can run. */
const VISION_MODELS = [
  "gemini-3.5-flash",
  "gemini-3.1-pro-preview",
  "gemini-2.5-pro",
  "gemini-2.5-flash",
  "claude-opus-4-8",
  "claude-sonnet-4-6",
  "gpt-5.5",
  "gpt-5.4",
];

// Defaults are best-for-task, DERIVED from routing (Claude for reasoning roles,
// Gemini for media) — the picker shows these until the user chooses otherwise.
// Selection is PER ROLE: 5 selectable + 2 system-managed (verifier, filter).
export const SEED_MODEL_CONFIG: LayerModelConfig[] = [
  {
    layer: "orchestrator",
    label: "Orchestrator",
    description: "Plans the run, routes experts, streams the decision log.",
    model: "claude-haiku-4-5",
    default: "claude-haiku-4-5",
    options: SELECTABLE_MODELS,
  },
  {
    layer: "research",
    label: "Research",
    description: "Gathers and cross-checks sources across the open web.",
    model: "claude-haiku-4-5",
    default: "claude-haiku-4-5",
    options: SELECTABLE_MODELS,
  },
  {
    layer: "planner",
    label: "Writing & planning",
    description: "Synthesizes the findings into the structured draft.",
    model: "claude-sonnet-4-6",
    default: "claude-sonnet-4-6",
    options: SELECTABLE_MODELS,
  },
  {
    layer: "code",
    label: "Code & data",
    description: "Writes and runs code, and does the data analysis.",
    model: "claude-sonnet-4-6",
    default: "claude-sonnet-4-6",
    options: SELECTABLE_MODELS,
  },
  {
    layer: "media_expert",
    label: "Media & documents",
    description: "Reads images, audio, video, and documents — vision-capable models only.",
    model: "gemini-2.5-flash",
    default: "gemini-2.5-flash",
    options: VISION_MODELS,
  },
  {
    layer: "verifier",
    label: "Verifier",
    description:
      "Security gate on every input. System-managed — part of the pipeline's safety guarantee, not a preference.",
    model: "gemini-2.5-flash-lite",
    default: "gemini-2.5-flash-lite",
    options: [],
    locked: true,
  },
  {
    layer: "filter",
    label: "Output filter",
    description:
      "Groundedness and policy gate on every report. System-managed for the same reason as the verifier.",
    model: "gemini-2.5-flash-lite",
    default: "gemini-2.5-flash-lite",
    options: [],
    locked: true,
  },
];
