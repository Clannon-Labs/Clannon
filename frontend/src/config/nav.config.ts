/**
 * Navigation structure — add, remove, rename, or reorder links here
 * and the marketing header, footer, and workspace sidebar/bottom-bar
 * all follow.
 */

import { History, LayoutGrid, Target, Settings, type LucideIcon } from "lucide-react";

export interface MarketingNavItem {
  href: string;
  label: string;
}

/** Marketing header + footer "Product" column. */
export const MARKETING_NAV: MarketingNavItem[] = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#memory", label: "Memory" },
  { href: "/#pricing", label: "Pricing" },
];

export interface AppNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

/** Workspace sidebar (desktop) and bottom navigation (mobile). */
export const APP_NAV: AppNavItem[] = [
  { href: "/app", label: "Workspace", icon: LayoutGrid, exact: true },
  { href: "/app/memory", label: "Memory", icon: Target },
  { href: "/app/history", label: "History", icon: History },
  { href: "/app/settings", label: "Settings", icon: Settings },
];
