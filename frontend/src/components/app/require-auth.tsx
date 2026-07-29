"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useMe } from "@/lib/api/hooks";

export function RequireAuth({
  children,
  fallback,
}: {
  children: ReactNode;
  fallback: ReactNode;
}) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
