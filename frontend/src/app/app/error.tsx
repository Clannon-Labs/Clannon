"use client";

import { Button } from "@/components/ui/button";

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-2xl py-16 text-center">
      <h1 className="display-soft text-xl text-foreground">Something went wrong</h1>
      <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
        A workspace error interrupted this view. Your archive and data are safe.
        {error.digest && (
          <span className="mt-2 block font-mono text-[12px] text-faint">
            ref: {error.digest}
          </span>
        )}
      </p>
      <Button size="lg" className="mt-8" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
