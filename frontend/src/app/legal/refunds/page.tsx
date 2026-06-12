import type { Metadata } from "next";
import { siteConfig } from "@/config/site.config";
import { LegalDoc } from "@/components/legal/legal-doc";

export const metadata: Metadata = { title: "Refund & Cancellation Policy" };

const c = siteConfig;

export default function RefundsPage() {
  return (
    <LegalDoc
      title="Refund & Cancellation Policy"
      intro="Billing should never be the reason you distrust a product. This is the whole policy, without fine print."
    >
      <h2>1. Cancelling</h2>
      <ul>
        <li>
          Cancel anytime from Settings → Billing. No emails, no retention
          calls.
        </li>
        <li>
          Cancellation takes effect at the end of your current billing
          period; you keep full access and your remaining token budget until
          then.
        </li>
        <li>
          After cancellation your account drops to the free plan. Your data
          stays until you delete it — episodic memory keeps working on the
          free tier, and your wiki remains exportable as markdown.
        </li>
      </ul>

      <h2>2. Refunds on your first subscription</h2>
      <p>
        If {c.name} isn&apos;t what you expected, your first subscription
        payment is refundable within {c.legal.refundWindowDays} days of
        purchase, provided you have used less than{" "}
        {c.legal.refundUsageCeilingPct}% of the plan&apos;s token budget. That
        ceiling exists because tokens spent are costs we have already paid to
        model providers — but a real look around the product will not
        disqualify you.
      </p>

      <h2>3. Renewals</h2>
      <p>
        Renewal payments are generally not refundable, with two exceptions:
      </p>
      <ul>
        <li>
          <strong>Our fault:</strong> if a service problem on our side
          materially prevented you from using the period you paid for, we
          refund it — partially or fully, in proportion to the disruption.
        </li>
        <li>
          <strong>Forgotten renewal:</strong> if you cancel within 72 hours
          of an automatic renewal and have not used the new period&apos;s
          budget, we refund that renewal.
        </li>
      </ul>

      <h2>4. What is never charged</h2>
      <ul>
        <li>
          Runs blocked by the security pipeline before model work begins
          consume no tokens.
        </li>
        <li>
          Runs that fail because of a pipeline error on our side are
          re-credited automatically.
        </li>
      </ul>

      <h2>5. Plan changes</h2>
      <ul>
        <li>
          <strong>Upgrades</strong> apply immediately; you pay the prorated
          difference and receive the larger budget at once.
        </li>
        <li>
          <strong>Downgrades</strong> apply at your next billing date so you
          never lose budget you already paid for.
        </li>
      </ul>

      <h2>6. Statutory rights</h2>
      <p>
        Nothing here limits rights you hold under the consumer-protection law
        that applies where you live. Where local law grants you stronger
        withdrawal or refund rights, those apply.
      </p>

      <h2>7. How to request a refund</h2>
      <p>
        Email <a href={`mailto:${c.contact.support}`}>{c.contact.support}</a>{" "}
        from your account address with the invoice reference. Refunds are
        processed to the original payment method through Stripe, normally
        within 5–10 business days.
      </p>
    </LegalDoc>
  );
}
