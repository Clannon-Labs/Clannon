"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import { MailCheck } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const schema = z.string().email("Enter a valid email address.");

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const parsed = schema.safeParse(email);
    if (!parsed.success) {
      setError(parsed.error.issues[0].message);
      return;
    }
    setError(undefined);
    setSubmitting(true);
    // Always resolves to the same state — never reveals whether an
    // account exists for this address.
    await new Promise((r) => setTimeout(r, 700));
    setSent(true);
  }

  if (sent) {
    return (
      <div className="animate-fade-up text-center">
        <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
        <h1 className="display-soft mt-5 text-2xl">
          Check your inbox
        </h1>
        <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
          If an account exists for <span className="font-medium text-foreground">{email}</span>,
          a reset link is on its way. It expires in 30 minutes.
        </p>
        <ButtonLink href="/login" variant="outline" className="mt-8">
          Back to sign in
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <h1 className="display-soft text-3xl">
        Reset your password
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Enter your email and we&apos;ll send a reset link.
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-8 flex flex-col gap-5">
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
        <Button type="submit" size="lg" loading={submitting}>
          {submitting ? "Sending…" : "Send reset link"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Remembered it?{" "}
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
