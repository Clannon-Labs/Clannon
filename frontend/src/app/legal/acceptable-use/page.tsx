import type { Metadata } from "next";
import { siteConfig } from "@/config/site.config";
import { LegalDoc } from "@/components/legal/legal-doc";

export const metadata: Metadata = { title: "Acceptable Use Policy" };

const c = siteConfig;

export default function AcceptableUsePage() {
  return (
    <LegalDoc
      title="Acceptable Use Policy"
      intro={`${c.name} automates research. That power has edges. This policy draws them — it applies to every run, upload, and memory entry, and it is part of the Terms of Service.`}
    >
      <h2>1. Prohibited uses</h2>
      <p>You may not use the service to:</p>
      <ul>
        <li>
          <strong>Break the law</strong> — research in furtherance of fraud,
          unlawful surveillance, or any other illegal activity.
        </li>
        <li>
          <strong>Profile private individuals</strong> — compiling dossiers on
          people who are not public figures without a lawful basis. The
          pipeline blocks briefs containing bulk unredacted personal data for
          exactly this reason; do not try to work around it.
        </li>
        <li>
          <strong>Violate others&apos; rights</strong> — submitting content you
          have no right to use, or producing deliverables that infringe
          intellectual property.
        </li>
        <li>
          <strong>Target or harass</strong> — research designed to harass,
          stalk, or intimidate any person or group.
        </li>
        <li>
          <strong>Attack the platform</strong> — probing or bypassing the
          security pipeline, attempting prompt-injection against the
          orchestrator or other tenants, scraping the service, or
          circumventing rate limits and token budgets.
        </li>
        <li>
          <strong>Distribute malware</strong> — uploading malicious files.
          (They are scanned and blocked before processing; attempting it is
          still a violation.)
        </li>
        <li>
          <strong>Resell without agreement</strong> — offering the service
          itself to third parties as your own product. Delivering reports to
          your clients is what the product is for and is always fine.
        </li>
      </ul>

      <h2>2. High-stakes research</h2>
      <p>
        Output that informs medical, legal, financial, or safety-critical
        decisions must be reviewed by a qualified human before use. The
        quality filter verifies citations; it does not replace professional
        judgment.
      </p>

      <h2>3. Fair use of shared infrastructure</h2>
      <p>
        Token budgets are the primary limiter, but patterns that degrade the
        service for others — automated request flooding, deliberately
        pathological inputs — may be rate-limited or blocked even within
        budget.
      </p>

      <h2>4. Enforcement</h2>
      <p>
        Violations are handled proportionally: most result in a warning and a
        blocked run; serious or repeated violations lead to suspension or
        termination as described in the Terms of Service. Where the law
        requires it, we report unlawful activity to authorities.
      </p>

      <h2>5. Reporting abuse</h2>
      <p>
        If you believe someone is misusing the service, contact{" "}
        <a href={`mailto:${c.contact.support}`}>{c.contact.support}</a>. We
        investigate every report.
      </p>
    </LegalDoc>
  );
}
