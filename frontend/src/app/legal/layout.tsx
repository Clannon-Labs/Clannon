import type { ReactNode } from "react";
import { MarketingHeader } from "@/components/marketing/header";
import { MarketingFooter } from "@/components/marketing/footer";

export default function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <MarketingHeader />
      <main id="main" className="flex-1">{children}</main>
      <MarketingFooter />
    </>
  );
}
