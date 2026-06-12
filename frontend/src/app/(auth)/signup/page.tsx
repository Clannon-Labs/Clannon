"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { getClient, ApiError } from "@/lib/api";
import { queryKeys } from "@/lib/api/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiModeNotice } from "@/components/auth/mode-notice";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { siteConfig } from "@/config/site.config";

const schema = z.object({
  name: z.string().min(2, "Tell us what to call you."),
  email: z.string().email("Enter a valid email address."),
  password: z
    .string()
    .min(
      siteConfig.auth.passwordMinLength,
      `Use at least ${siteConfig.auth.passwordMinLength} characters.`,
    ),
});

export default function SignupPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [values, setValues] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Partial<typeof values>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const validateField = (field: keyof typeof values) => {
    const result = schema.shape[field].safeParse(values[field]);
    setErrors((e) => ({
      ...e,
      [field]: result.success ? undefined : result.error.issues[0].message,
    }));
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      const next: Partial<typeof values> = {};
      for (const issue of parsed.error.issues) {
        next[issue.path[0] as keyof typeof values] = issue.message;
      }
      setErrors(next);
      // WCAG focus management — put the keyboard where the problem is
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

        <p className="text-center text-[12.5px] leading-relaxed text-faint">
          By creating a workspace you agree to the{" "}
          <Link href="/legal/terms" className="underline underline-offset-2 hover:text-foreground">
            Terms of Service
          </Link>{" "}
          and{" "}
          <Link href="/legal/privacy" className="underline underline-offset-2 hover:text-foreground">
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
