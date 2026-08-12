"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import { MailX, MailCheck } from "lucide-react";
import { getClient, ApiError } from "@/lib/api";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const schema = z.string().email("Enter a valid email address.");

/**
 * Redirect target for `GET /waitlist/verify` when the token is unknown,
 * expired, or already used (`backend/api/waitlist.py` — the three are
 * indistinguishable by design, so this copy can't say which). Distinct from
 * an invalid/expired APPROVAL token on /signup — that's a different backend
 * message and a different next action (there's no "resend" for an approval).
 */
export default function WaitlistInvalidLinkPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const parsed = schema.safeParse(email);
    if (!parsed.success) {
      setError(parsed.error.issues[0].message);
      return;
    }
    setError(undefined);
    setSubmitting(true);
    try {
      await getClient().resendWaitlistVerification(parsed.data);
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
          If that address is on the waitlist and still unconfirmed, a fresh link is on
          its way.
        </p>
        <ButtonLink href="/" variant="outline" className="mt-8">
          Back to the site
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="animate-fade-up text-center">
      <MailX className="mx-auto size-10 text-destructive" aria-hidden />
      <h1 className="display-soft mt-5 text-2xl">Link expired</h1>
      <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
        That confirmation link is invalid or has already been used. Enter your email
        below and we&apos;ll send a new one.
      </p>

      <form onSubmit={onSubmit} noValidate className="mx-auto mt-6 flex max-w-xs flex-col gap-4 text-left">
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
          value={email}
          error={error}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Button type="submit" loading={submitting}>
          {submitting ? "Sending…" : "Resend confirmation link"}
        </Button>
      </form>

      <p className="mt-6 text-sm text-muted-foreground">
        Not on the waitlist yet?{" "}
        <Link
          href="/waitlist"
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          Join
        </Link>
      </p>
    </div>
  );
}
