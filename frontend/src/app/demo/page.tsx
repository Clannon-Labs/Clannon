import type { Metadata } from "next";
import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Mark } from "@/components/brand/logo";
import { DemoConversation } from "@/components/marketing/demo-conversation";
import { siteConfig } from "@/config/site.config";

export const metadata: Metadata = {
  title: "Live demo",
  description:
    "Watch Clannon run a real research pipeline — no signup. Pick a starter and see the routing, the experts working in parallel, and the quality filter, start to finish.",
};

/**
 * The public, no-signup demo. A chat exactly like the workspace, but you can
 * only pick from pre-defined starters — the run is canned and isolated, so it
 * never costs anything. The slim app-style header (not the marketing chrome)
 * makes it read as "a real run," with sign-up always one tap away.
 */
export default function DemoPage() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-background/90 px-4 backdrop-blur-md sm:px-6">
        <Link href="/" className="flex items-center gap-2" aria-label={`${siteConfig.name} home`}>
          <Mark className="size-5 text-primary" aria-hidden />
          <span className="font-display text-base font-medium">{siteConfig.name}</span>
          <span className="tag-label ml-1 rounded-full border border-border px-2 py-0.5 text-faint">
            Demo
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <Link href="/login" className="text-[13px] text-muted-foreground transition-colors hover:text-foreground">
            Sign in
          </Link>
          <ButtonLink href="/signup" size="sm">
            Start free
          </ButtonLink>
        </div>
      </header>
      <main id="main">
        <DemoConversation />
      </main>
    </div>
  );
}
