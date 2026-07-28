import "server-only";

import { PLANS, type Plan } from "@/config/plans";

const CONFIG_TIMEOUT_MS = 1_500;

function isPlan(value: unknown): value is Plan {
  if (!value || typeof value !== "object") return false;
  const plan = value as Partial<Plan>;
  return (
    typeof plan.id === "string" &&
    typeof plan.name === "string" &&
    typeof plan.monthlyUsd === "number" &&
    typeof plan.tokenBudget === "number" &&
    typeof plan.tagline === "string" &&
    Array.isArray(plan.memoryTiers) &&
    Array.isArray(plan.features)
  );
}

/**
 * Public pricing belongs to server-rendered marketing, not client Query state.
 * Backend remains authoritative in HTTP mode; bounded local fallback keeps
 * marketing available during deploys and local mock work.
 */
export async function getPublicPlans(): Promise<Plan[]> {
  if (process.env.NEXT_PUBLIC_API_MODE !== "http") return PLANS;

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${baseUrl}/config`, {
      signal: AbortSignal.timeout(CONFIG_TIMEOUT_MS),
      next: { revalidate: 300 },
    });
    if (!response.ok) return PLANS;
    const body = (await response.json()) as { plans?: unknown };
    return Array.isArray(body.plans) && body.plans.length > 0 && body.plans.every(isPlan)
      ? body.plans
      : PLANS;
  } catch {
    return PLANS;
  }
}
