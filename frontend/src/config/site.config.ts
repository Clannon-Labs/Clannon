/**
 * Site identity, contact, auth, and legal configuration.
 *
 * Everything in this file is intentionally changeable without touching
 * components: brand copy, support emails, OAuth providers, legal entity
 * details. If a value might ever appear on a page, it belongs here —
 * not hardcoded in a component.
 *
 * Companion files:
 *   app.config.ts — API mode, backend base URL, every endpoint path
 *   plans.ts      — subscription plans, prices, token budgets, tiers
 */

export type OAuthProvider = "google" | "github" | "apple";

export const siteConfig = {
  /** Product name used in the wordmark, titles, metadata, and legal text. */
  name: "Clannon",
  tagline: "research that remembers",
  description:
    "Clannon turns a client brief into a sourced, quality-filtered research report — with a memory that grows with every project. Built for freelancers and small agencies.",

  /** Public site origin (canonical URLs, OG metadata). */
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",

  /**
   * Contact addresses surfaced in the UI and the legal documents.
   * Replace these when the real mail domain exists.
   */
  contact: {
    support: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@clannon.app",
    privacy: process.env.NEXT_PUBLIC_PRIVACY_EMAIL ?? "privacy@clannon.app",
    legal: process.env.NEXT_PUBLIC_LEGAL_EMAIL ?? "legal@clannon.app",
  },

  auth: {
    /**
     * Sign-in methods shown on the auth pages, in order. "password" is
     * the email+password form; the rest render as OAuth buttons. Remove
     * an entry here and its button disappears everywhere.
     */
    providers: ["password", "google", "github"] as ("password" | OAuthProvider)[],
    passwordMinLength: 8,
  },

  footer: {
    /** Short line in the footer's bottom bar. Empty string hides it. */
    credit: "research that remembers",
    /** Engine credit shown under the wordmark. Empty string hides it. */
    engineLine: "Powered by the Vraksha engine.",
  },

  /**
   * Values interpolated into the legal documents (/legal/*). Set the
   * real legal entity and jurisdiction before going to production —
   * the documents fall back to neutral wording while these are unset.
   */
  legal: {
    /** Registered legal entity operating the service. */
    entityName: "Clannon",
    /** ISO date the current legal documents took effect. */
    effectiveDate: "2026-06-11",
    /**
     * Governing law / jurisdiction, e.g. "the courts of Singapore".
     * Leave empty to use neutral "the jurisdiction in which the
     * operator is established" wording.
     */
    governingLaw: "",
    /** Minimum age to use the service. */
    minimumAge: 16,
    /** Days within which account data is purged after deletion. */
    deletionWindowDays: 30,
    /** First-subscription refund window and usage ceiling. */
    refundWindowDays: 14,
    refundUsageCeilingPct: 10,
  },

  /**
   * Third-party processors disclosed in the privacy policy. Keep this
   * list in sync with what the backend actually uses.
   */
  subprocessors: [
    { name: "Vercel", purpose: "Web application hosting" },
    { name: "Railway", purpose: "Backend API hosting" },
    { name: "Supabase", purpose: "Primary database and authentication" },
    { name: "Qdrant Cloud", purpose: "Vector storage for the memory system" },
    { name: "Upstash", purpose: "Session cache and usage metering" },
    { name: "Cloudflare R2", purpose: "Wiki file storage" },
    { name: "Stripe", purpose: "Payment processing (card data never touches our servers)" },
    { name: "Google (Gemini API)", purpose: "AI model inference" },
    { name: "Anthropic / other model providers", purpose: "AI model inference, when selected in model settings" },
  ],
} as const;

export type SiteConfig = typeof siteConfig;
