import type { Metadata } from "next";
import type { ReactNode } from "react";
import { CommandPalette } from "@/components/app/command-palette";
import { RequireAuth } from "@/components/app/require-auth";
import { Sidebar } from "@/components/app/sidebar";

export const metadata: Metadata = {
  title: "Workspace",
  robots: { index: false, follow: false },
};

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <RequireAuth>
        <Sidebar />
        <CommandPalette />
        <main id="main" className="px-4 pb-24 pt-20 sm:px-6 md:ml-60 md:pb-10 md:pt-8 lg:px-10">
          {children}
        </main>
      </RequireAuth>
    </div>
  );
}
