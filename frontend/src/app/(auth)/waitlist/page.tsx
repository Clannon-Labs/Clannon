"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import { MailCheck } from "lucide-react";
import { getClient, ApiError } from "@/lib/api";
import { appConfig } from "@/config/app.config";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  note: z.string().max(1000, "Keep it under 1,000 characters.").optional(),
});

export default function WaitlistPage() {
  const [values, setValues] = useState({ email: "", note: "" });
  const [error, setError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      setError(parsed.error.issues[0].message);
      return;
    }
    setError(undefined);
    setSubmitting(true);
    try {
      await getClient().joinWaitlist({
        email: parsed.data.email,
        note: parsed.data.note?.trim() || undefined,
      });
      // Always the same outcome regardless of what the backend actually did
      // with this address — join/resend never disclose list membership (see
      // specification/api/ROUTES.md §Waitlist). "You're on the list!" would
      // be a claim the frontend can't verify; this copy only says what's
      // true either way — a link went out if it could.
      setSent(true);
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong — try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <div className="animate-fade-up text-center">
        <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
        <h1 className="display-soft mt-5 text-2xl">Check your inbox</h1>
        <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
          If that address can join, we&apos;ve sent a confirmation link to{" "}
          <span className="font-medium text-foreground">{values.email}</span>. Confirming
          it puts you on the list — the owner reviews requests individually and emails
          you when a spot opens.
        </p>
        {appConfig.apiMode === "mock" && (
          <p className="mx-auto mt-6 max-w-xs rounded-md border border-border bg-surface px-4 py-3 text-left text-[12px] leading-relaxed text-muted-foreground">
            <span className="mr-2 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
              Demo
            </span>
            No real inbox in mock mode. See{" "}
            <Link href="/waitlist/confirmed" className="underline underline-offset-2 hover:text-foreground">
              /waitlist/confirmed
            </Link>{" "}
            for what the verify link leads to, or skip straight to the approved state at{" "}
            <Link
              href="/signup?approvalToken=demo-approved"
              className="underline underline-offset-2 hover:text-foreground"
            >
              /signup?approvalToken=demo-approved
            </Link>
            .
          </p>
        )}
        <ButtonLink href="/login" variant="outline" className="mt-8">
          Back to sign in
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <h1 className="display text-[2.4rem] leading-[1.0]">Join the waitlist</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Clannon is in a private alpha. Leave your email and we&apos;ll reach out when
        there&apos;s room.
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-8 flex flex-col gap-5">
        {formError && (
          <p
            role="alert"
            className="rounded-md border border-destructive/30 bg-destructive-soft px-4 py-3 text-sm text-destructive"
          >
            {formError}
          </p>
        )}

        <Input
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          placeholder="you@studio.com"
          value={values.email}
          error={error}
          onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
          required
        />

        <Textarea
          label="What are you hoping to use it for? (optional)"
          name="note"
          rows={3}
          maxLength={1000}
          placeholder="A line or two helps us prioritize invites."
          value={values.note}
          onChange={(e) => setValues((v) => ({ ...v, note: e.target.value }))}
        />

        <Button type="submit" size="lg" loading={submitting}>
          {submitting ? "Sending…" : "Join the waitlist"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already approved?{" "}
        <Link
          href="/login"
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}
