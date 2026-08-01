import type { Metadata } from "next";
import Link from "next/link";
import { siteConfig } from "@/config/site.config";
import { LegalDoc, governingLawText } from "@/components/legal/legal-doc";

export const metadata: Metadata = { title: "Terms of Service" };

const c = siteConfig;

export default function TermsPage() {
  return (
    <LegalDoc
      title="Terms of Service"
      intro={`These terms are the agreement between you and ${c.legal.entityName} for using ${c.name}. By creating a workspace or running research, you accept them.`}
    >
      <h2>1. The service</h2>
      <p>
        {c.name} is an automated research platform: you submit a brief, a
        pipeline of AI agents researches it, and you receive a sourced report
        while the system maintains a memory of your work. The service
        includes the web dashboard, the research pipeline, and the memory
        system.
      </p>

      <h2>2. Accounts</h2>
      <ul>
        <li>You must provide accurate account information and keep your credentials secure. Activity under your account is your responsibility.</li>
        <li>You must be at least {c.legal.minimumAge} years old.</li>
        <li>One person or organization per account unless your plan includes team seats.</li>
      </ul>

      <h2>3. Plans, token budgets, and billing</h2>
      <ul>
        <li>
          Paid plans include a token budget for each fixed billing period.
          Budgets reset on your billing anniversary; unused tokens do not roll over.
        </li>
        <li>
          Before creating a root, follow-up, or revision run, the server checks
          completed usage against confirmed entitlement. One already-admitted
          run may overshoot; exact concurrent and per-call hard stops are not live.
          Runs blocked before model work begins do not consume your budget.
        </li>
        <li>
          During private alpha, billing changes remain pending until server-side
          operator confirmation. Cancellation and refunds are covered by the{" "}
          <Link href="/legal/refunds">Refund &amp; Cancellation Policy</Link>.
        </li>
        <li>We will give at least 30 days&apos; notice before any price increase affects you.</li>
      </ul>

      <h2>4. Your content and your rights to it</h2>
      <ul>
        <li>
          You own what you put in (briefs, files, wiki entries) and what the
          pipeline produces for you (reports). We claim no ownership over
          either.
        </li>
        <li>
          You grant us the limited license needed to operate the service:
          processing your content through the pipeline, storing it, and
          deriving your account-scoped memory from it. Nothing more.
        </li>
        <li>
          You are responsible for having the right to submit what you submit
          — client materials included.
        </li>
      </ul>

      <h2>5. AI output — read this one</h2>
      <p>
        Reports are produced by AI systems with a quality filter that checks
        citations and grounding. That filter reduces errors; it does not
        eliminate them. <strong>AI output can be wrong, incomplete, or out of
        date.</strong> You must review reports before relying on them or
        delivering them to your own clients. Reports are not legal,
        financial, medical, or other professional advice.
      </p>

      <h2>6. Acceptable use</h2>
      <p>
        Use of the service is subject to the{" "}
        <Link href="/legal/acceptable-use">Acceptable Use Policy</Link>, which
        is part of these terms.
      </p>

      <h2>7. Availability and changes to the service</h2>
      <p>
        We aim for high availability but do not guarantee uninterrupted
        service. We may change or retire features; if a change materially
        reduces what your paid plan provides, you may cancel and receive a
        prorated refund for the unused period.
      </p>

      <h2>8. Termination</h2>
      <ul>
        <li>You may close your account at any time; data deletion follows the Privacy Policy.</li>
        <li>
          We may suspend or terminate accounts that violate these terms or
          the Acceptable Use Policy. Unless the violation is severe or
          unlawful, we will warn you and give you a chance to export your
          data first.
        </li>
      </ul>

      <h2>9. Liability</h2>
      <p>
        To the maximum extent permitted by law: the service is provided “as
        is”; we are not liable for indirect or consequential damages or for
        decisions made in reliance on AI output; and our total liability is
        capped at the amount you paid us in the 12 months before the claim.
        Nothing in these terms limits liability that cannot lawfully be
        limited.
      </p>

      <h2>10. Governing law</h2>
      <p>
        These terms are governed by the law of {governingLawText()}. We will
        always attempt to resolve disputes informally first — write to{" "}
        <a href={`mailto:${c.contact.legal}`}>{c.contact.legal}</a>.
      </p>

      <h2>11. Changes to these terms</h2>
      <p>
        We will notify you by email at least 14 days before material changes
        take effect. Continuing to use the service after that date means you
        accept the updated terms; if you do not, you may cancel with a
        prorated refund.
      </p>
    </LegalDoc>
  );
}
