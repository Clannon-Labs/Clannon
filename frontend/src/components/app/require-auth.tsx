"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useMe } from "@/lib/api/hooks";
import { Mark } from "@/components/brand/logo";

export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background">
        <Mark className="size-10 animate-pulse-dot text-primary" />
        <span className="sr-only">Loading your workspace</span>
      </div>
    );
  }

  return <>{children}</>;
}
