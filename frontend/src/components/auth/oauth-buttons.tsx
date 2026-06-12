"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { siteConfig, type OAuthProvider } from "@/config/site.config";
import { getClient, ApiError } from "@/lib/api";
import { queryKeys } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.39 3.62v3h3.87c2.26-2.09 3.57-5.17 3.57-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.87-3c-1.07.72-2.45 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.29v3.1A11.99 11.99 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.29 14.29a7.2 7.2 0 0 1 0-4.58V6.6H1.29a12.04 12.04 0 0 0 0 10.8l4-3.11Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.77c1.76 0 3.34.6 4.58 1.79l3.43-3.43A11.53 11.53 0 0 0 12 0 11.99 11.99 0 0 0 1.29 6.6l4 3.11C6.23 6.88 8.88 4.77 12 4.77Z"
      />
    </svg>
  );
}

function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("fill-current", className)} aria-hidden>
      <path d="M12 .3a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.04c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.33-1.76-1.33-1.76-1.09-.74.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5 1 .1-.78.42-1.31.76-1.61-2.66-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.11-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6.01 0c2.29-1.55 3.3-1.23 3.3-1.23.65 1.66.24 2.88.12 3.18.77.84 1.23 1.91 1.23 3.22 0 4.61-2.81 5.62-5.49 5.92.43.37.81 1.1.81 2.23v3.3c0 .32.22.7.83.58A12 12 0 0 0 12 .3Z" />
    </svg>
  );
}

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("fill-current", className)} aria-hidden>
      <path d="M16.36 12.94c.03 3.05 2.68 4.07 2.71 4.08-.02.07-.42 1.45-1.4 2.87-.84 1.23-1.71 2.45-3.09 2.48-1.35.02-1.79-.8-3.33-.8-1.55 0-2.03.77-3.31.83-1.33.05-2.34-1.33-3.19-2.55-1.73-2.5-3.05-7.07-1.28-10.16.88-1.53 2.46-2.5 4.17-2.52 1.3-.03 2.53.88 3.33.88.79 0 2.29-1.09 3.86-.93.66.03 2.5.27 3.69 2-.1.06-2.2 1.28-2.16 3.82ZM13.8 4.25c.7-.85 1.18-2.04 1.05-3.22-1.01.04-2.24.68-2.97 1.53-.65.75-1.22 1.96-1.07 3.11 1.13.09 2.28-.57 2.99-1.42Z" />
    </svg>
  );
}

const PROVIDER_META: Record<OAuthProvider, { label: string; Icon: typeof GoogleIcon }> = {
  google: { label: "Google", Icon: GoogleIcon },
  github: { label: "GitHub", Icon: GitHubIcon },
  apple: { label: "Apple", Icon: AppleIcon },
};

/**
 * OAuth sign-in buttons. Which providers appear (and their order) is
 * controlled by siteConfig.auth.providers — no code change needed to
 * add or remove one.
 */
export function OAuthButtons({ intent }: { intent: "sign in" | "sign up" }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [pending, setPending] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  const providers = siteConfig.auth.providers.filter(
    (p): p is OAuthProvider => p !== "password",
  );
  const hasPassword = siteConfig.auth.providers.includes("password");

  if (providers.length === 0) return null;

  async function start(provider: OAuthProvider) {
    setError(null);
    setPending(provider);
    try {
      const user = await getClient().loginWithProvider(provider);
      qc.setQueryData(queryKeys.me, user);
      router.push("/app");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `Could not ${intent} with ${PROVIDER_META[provider].label} — try again.`,
      );
      setPending(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <p role="alert" className="text-[13px] text-destructive">
          {error}
        </p>
      )}
      {providers.map((provider) => {
        const { label, Icon } = PROVIDER_META[provider];
        return (
          <button
            key={provider}
            type="button"
            disabled={pending !== null}
            onClick={() => start(provider)}
            className={cn(
              "inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2.5 rounded-md",
              "border border-border-strong bg-surface-raised text-[14px] font-medium text-foreground",
              "transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50",
            )}
          >
            {pending === provider ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Icon className="size-4" />
            )}
            Continue with {label}
          </button>
        );
      })}
      {hasPassword && (
        <div className="my-2 flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-border" />
          <span className="tag-label text-faint">or with email</span>
          <span className="h-px flex-1 bg-border" />
        </div>
      )}
    </div>
  );
}
