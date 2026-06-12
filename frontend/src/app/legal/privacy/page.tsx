import type { Metadata } from "next";
import { siteConfig } from "@/config/site.config";
import { LegalDoc } from "@/components/legal/legal-doc";

export const metadata: Metadata = { title: "Privacy Policy" };

const c = siteConfig;

export default function PrivacyPolicyPage() {
  return (
    <LegalDoc
      title="Privacy Policy"
      intro={`This policy explains what ${c.name} collects, why, who processes it, and the rights you have over it. It is written to be accurate about how the system actually works — including the parts involving AI model providers.`}
    >
      <h2>1. Who is responsible</h2>
      <p>
        The service is operated by {c.legal.entityName} (“we”, “us”). For
        anything in this policy, contact{" "}
        <a href={`mailto:${c.contact.privacy}`}>{c.contact.privacy}</a>. We
        respond to every privacy request, normally within 7 days.
      </p>

      <h2>2. What we collect</h2>
      <ul>
        <li>
          <strong>Account data</strong> — your name, email address, and
          password hash (or your OAuth identity if you sign in with a
          provider). We never see or store OAuth passwords.
        </li>
        <li>
          <strong>Research content</strong> — the briefs you submit, files you
          attach, and the reports the pipeline produces for you.
        </li>
        <li>
          <strong>Memory data</strong> — the wiki entries you write and the
          episodic, semantic, and procedural memories the system derives from
          your runs. All of it is scoped to your account.
        </li>
        <li>
          <strong>Usage data</strong> — token consumption, run counts, and
          plan state, used for budget enforcement and billing.
        </li>
        <li>
          <strong>Technical data</strong> — IP address, browser type, and
          security logs (rate limiting, abuse prevention). Kept no longer
          than 90 days unless investigating abuse.
        </li>
        <li>
          <strong>Payment data</strong> — handled entirely by Stripe. Card
          numbers never touch our servers; we store only the subscription
          state and invoice references Stripe gives us.
        </li>
      </ul>

      <h2>3. How research content is processed</h2>
      <p>
        This is the part most policies hide, so here it is plainly: to produce
        a report, your brief and related context are sent to third-party AI
        model providers (by default Google&apos;s Gemini API; others if you select
        them in model settings). Before any model sees your input, our
        sanitization layer scans it and strips detected secrets and flags
        personal data; runs containing unredacted personal data about third
        parties are blocked rather than processed. Model providers process
        this content under their API data-protection terms and do not use it
        to train their models under those terms.
      </p>
      <p>
        <strong>We do not train models on your content.</strong> We do not
        sell your data. We do not show you advertising.
      </p>

      <h2>4. Memory, retention, and deletion</h2>
      <ul>
        <li>
          Memory entries persist until you delete them — that is the point of
          the product. You can view and delete individual entries from the
          Memory page at any time; wiki memory is fully yours to edit.
        </li>
        <li>Your wiki exports as plain markdown whenever you want it.</li>
        <li>
          When you delete your account, all research content, memory data,
          and account data are purged within {c.legal.deletionWindowDays}{" "}
          days. Invoices are retained as long as tax law requires.
        </li>
      </ul>

      <h2>5. Who else processes data (subprocessors)</h2>
      <p>We use the following providers to run the service:</p>
      <ul>
        {c.subprocessors.map((s) => (
          <li key={s.name}>
            <strong>{s.name}</strong> — {s.purpose}.
          </li>
        ))}
      </ul>
      <p>
        Each processes data only to provide its function to us. We will
        update this list before adding a provider that handles your content.
      </p>

      <h2>6. Security</h2>
      <p>
        Data is encrypted in transit (TLS) and at rest. Database rows are
        scoped to your account at the database layer, not just in
        application code. Memory queries are filtered by account identity as
        a build-enforced rule. Sessions use httpOnly cookies — authentication
        tokens are never exposed to page scripts. The output filter checks
        final reports for personal-data leakage before delivery.
      </p>

      <h2>7. Cookies and local storage</h2>
      <p>
        We use one session cookie (httpOnly, required to keep you signed in)
        and local storage for interface preferences such as your theme. There
        are no advertising or cross-site tracking cookies, so there is no
        cookie banner — there is nothing to consent to beyond what the
        service needs to function.
      </p>

      <h2>8. Your rights</h2>
      <p>
        Wherever you are, we extend the same rights: access a copy of your
        data, correct it, export it (machine-readable), restrict processing,
        and delete it. Exercise any of these from your settings or by
        emailing <a href={`mailto:${c.contact.privacy}`}>{c.contact.privacy}</a>.
        If you believe we have mishandled your data, you may also complain to
        your local data-protection authority.
      </p>

      <h2>9. Age</h2>
      <p>
        The service is not directed at children and requires users to be at
        least {c.legal.minimumAge} years old.
      </p>

      <h2>10. Changes</h2>
      <p>
        If we change this policy in a way that affects your rights or how
        your content is processed, we will notify you by email before the
        change takes effect. The effective date at the top always reflects
        the current version.
      </p>
    </LegalDoc>
  );
}
