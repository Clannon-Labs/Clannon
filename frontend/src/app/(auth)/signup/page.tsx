"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { getClient, ApiError } from "@/lib/api";
import { queryKeys, useWaitlistEnabled } from "@/lib/api/hooks";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiModeNotice } from "@/components/auth/mode-notice";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { siteConfig } from "@/config/site.config";

const openSchema = z.object({
  name: z.string().min(2, "Tell us what to call you."),
  email: z.string().email("Enter a valid email address."),
  password: z
    .string()
    .min(
      siteConfig.auth.passwordMinLength,
      `Use at least ${siteConfig.auth.passwordMinLength} characters.`,
    ),
});

const approvedSchema = z.object({
  name: z.string().min(2, "Tell us what to call you."),
  password: z
    .string()
    .min(
      siteConfig.auth.passwordMinLength,
      `Use at least ${siteConfig.auth.passwordMinLength} characters.`,
    ),
});

/** No token, waitlist on — the invite-only state (owner ruling 2026-08-09). */
function GatedState() {
  return (
    <div className="animate-fade-up">
      <h1 className="display text-[2.4rem] leading-[1.0]">Private alpha</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Clannon isn&apos;t open for self-serve signup right now. Join the waitlist and
        we&apos;ll email you an invite when there&apos;s room.
      </p>
      <ButtonLink href="/waitlist" size="lg" className="mt-8">
        Join the waitlist
      </ButtonLink>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
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

/**
 * `?approvalToken=` present — the owner approved this address (`waitlist_cli.py`)
 * and mailed the link. Backend takes the account's email FROM the token, not the
 * body (`app.py`'s signup()), so there's genuinely no address to show here —
 * see the "optional second ask" in the filed config proposal for the route that
 * would change that.
 */
function ApprovedSignupForm({ approvalToken }: { approvalToken: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [values, setValues] = useState({ name: "", password: "" });
  const [errors, setErrors] = useState<Partial<typeof values>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Distinct from GatedState and from /waitlist/invalid-link: this is a rejected
  // APPROVAL token specifically ("This invite link is invalid or has expired."),
  // and there's no resend for it — approval is a one-time owner action, not a
  // self-serve mail send.
  const [tokenRejected, setTokenRejected] = useState(false);

  const validateField = (field: keyof typeof values) => {
    const result = approvedSchema.shape[field].safeParse(values[field]);
    setErrors((e) => ({
      ...e,
      [field]: result.success ? undefined : result.error.issues[0].message,
    }));
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const parsed = approvedSchema.safeParse(values);
    if (!parsed.success) {
      const next: Partial<typeof values> = {};
      for (const issue of parsed.error.issues) {
        next[issue.path[0] as keyof typeof values] = issue.message;
      }
      setErrors(next);
      const form = e.currentTarget as HTMLFormElement;
      setTimeout(() => form.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    setSubmitting(true);
    try {
      const user = await getClient().signup({ ...parsed.data, approvalToken });
      qc.setQueryData(queryKeys.me, user);
      router.push("/app");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setTokenRejected(true);
        setSubmitting(false);
        return;
      }
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong — try again.",
      );
      setSubmitting(false);
    }
  }

  if (tokenRejected) {
    return (
      <div className="animate-fade-up text-center">
        <h1 className="display-soft text-2xl">Invite link expired</h1>
        <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
          This invite link is invalid or has already been used. If you think
          that&apos;s wrong, ask the owner to resend it.
        </p>
        <ButtonLink href="/waitlist" variant="outline" className="mt-8">
          Join the waitlist
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <h1 className="display text-[2.4rem] leading-[1.0]">You&apos;re in</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Set a password to finish creating your account for the address you
        confirmed. Episodic memory included forever.
      </p>

      {apiModeNotice}

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
          label="Name"
          name="name"
          autoComplete="name"
          placeholder="Your name"
          value={values.name}
          error={errors.name}
          onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
          onBlur={() => validateField("name")}
          required
        />

        <Input
          label="Password"
          type="password"
          name="password"
          autoComplete="new-password"
          hint={`At least ${siteConfig.auth.passwordMinLength} characters.`}
          value={values.password}
          error={errors.password}
          onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
          onBlur={() => validateField("password")}
          required
        />

        <Button type="submit" size="lg" loading={submitting} className="mt-1">
          {submitting ? "Creating workspace…" : "Create my workspace"}
        </Button>

        <p className="text-center text-[12px] leading-relaxed text-faint">
          By creating a workspace you agree to the{" "}
          <Link href="/legal/terms" className="whitespace-nowrap underline underline-offset-2 hover:text-foreground">
            Terms of Service
          </Link>{" "}
          and{" "}
          <Link href="/legal/privacy" className="whitespace-nowrap underline underline-offset-2 hover:text-foreground">
            Privacy Policy
          </Link>
          .
        </p>
      </form>
    </div>
  );
}

/** No token, waitlist off — today's original open form, unchanged. Reachable
 *  once `waitlistEnabled` is explicitly `false` (see useWaitlistEnabled). */
function OpenSignupForm() {
  const router = useRouter();
  const qc = useQueryClient();
  const [values, setValues] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Partial<typeof values>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const validateField = (field: keyof typeof values) => {
    const result = openSchema.shape[field].safeParse(values[field]);
    setErrors((e) => ({
      ...e,
      [field]: result.success ? undefined : result.error.issues[0].message,
    }));
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const parsed = openSchema.safeParse(values);
    if (!parsed.success) {
      const next: Partial<typeof values> = {};
      for (const issue of parsed.error.issues) {
        next[issue.path[0] as keyof typeof values] = issue.message;
      }
      setErrors(next);
      const form = e.currentTarget as HTMLFormElement;
      setTimeout(() => form.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    setSubmitting(true);
    try {
      const user = await getClient().signup(parsed.data);
      qc.setQueryData(queryKeys.me, user);
      router.push("/app");
    } catch (err) {
      // Backstop for the window before waitlistEnabled is real: if the flag
      // said "open" but the backend disagrees (403 = gated), don't dead-end
      // on a generic error — send them to the form that actually works.
      if (err instanceof ApiError && err.status === 403) {
        router.push("/waitlist");
        return;
      }
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong — try again.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <h1 className="display text-[2.4rem] leading-[1.0]">
        Plant the first ring
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Free plan, no card. Episodic memory included forever.
      </p>

      {apiModeNotice}

      <div className="mt-8">
        <OAuthButtons intent="sign up" />
      </div>

      <form onSubmit={onSubmit} noValidate className="mt-2 flex flex-col gap-5">
        {formError && (
          <p
            role="alert"
            className="rounded-md border border-destructive/30 bg-destructive-soft px-4 py-3 text-sm text-destructive"
          >
            {formError}
          </p>
        )}

        <Input
          label="Name"
          name="name"
          autoComplete="name"
          placeholder="Your name"
          value={values.name}
          error={errors.name}
          onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
          onBlur={() => validateField("name")}
          required
        />

        <Input
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          placeholder="you@studio.com"
          value={values.email}
          error={errors.email}
          onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
          onBlur={() => validateField("email")}
          required
        />

        <Input
          label="Password"
          type="password"
          name="password"
          autoComplete="new-password"
          hint={`At least ${siteConfig.auth.passwordMinLength} characters.`}
          value={values.password}
          error={errors.password}
          onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
          onBlur={() => validateField("password")}
          required
        />

        <Button type="submit" size="lg" loading={submitting} className="mt-1">
          {submitting ? "Creating workspace…" : "Create my workspace"}
        </Button>

        <p className="text-center text-[12px] leading-relaxed text-faint">
          By creating a workspace you agree to the{" "}
          <Link href="/legal/terms" className="whitespace-nowrap underline underline-offset-2 hover:text-foreground">
            Terms of Service
          </Link>{" "}
          and{" "}
          <Link href="/legal/privacy" className="whitespace-nowrap underline underline-offset-2 hover:text-foreground">
            Privacy Policy
          </Link>
          .
        </p>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
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

function SignupContent() {
  const searchParams = useSearchParams();
  const approvalToken = searchParams.get("approvalToken");
  const waitlistEnabled = useWaitlistEnabled();

  if (approvalToken) return <ApprovedSignupForm approvalToken={approvalToken} />;
  if (waitlistEnabled) return <GatedState />;
  return <OpenSignupForm />;
}

export default function SignupPage() {
  return (
    <Suspense>
      <SignupContent />
    </Suspense>
  );
}
