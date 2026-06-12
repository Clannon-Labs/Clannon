"use client";

import { Mark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-5 text-center">
      <Mark className="size-12 text-destructive opacity-70" />
      <h1 className="display mt-6 text-[2.4rem] leading-[1.0]">
        Something snapped
      </h1>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
        An unexpected error broke this view. Nothing in your archive was
        affected.
        {error.digest && (
          <span className="mt-2 block font-mono text-[12px] text-faint">
            ref: {error.digest}
          </span>
        )}
      </p>
      <Button className="mt-8" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
