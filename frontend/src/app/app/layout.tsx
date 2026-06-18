import type { Metadata } from "next";
import type { ReactNode } from "react";
import { RequireAuth } from "@/components/app/require-auth";
import { AppShell } from "@/components/app/app-shell";
import { ProjectProvider } from "@/components/app/project-provider";

export const metadata: Metadata = {
  title: "Workspace",
  robots: { index: false, follow: false },
};

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <RequireAuth>
        <ProjectProvider>
          <AppShell>{children}</AppShell>
        </ProjectProvider>
      </RequireAuth>
    </div>
  );
}
