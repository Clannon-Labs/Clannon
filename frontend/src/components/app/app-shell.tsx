"use client";

import { useState, type ReactNode } from "react";
import { CommandPalette } from "@/components/app/command-palette";
import { NewProjectDialog } from "@/components/app/new-project-dialog";
import { Sidebar } from "@/components/app/sidebar";
import { cn } from "@/lib/utils";

const COLLAPSE_KEY = "clannon.sidebar.collapsed";

function readCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * The authed shell: the sidebar and the main column, with a collapsible rail.
 * Only ever mounts client-side (behind RequireAuth's loading gate), so reading
 * the persisted collapse state in the initialiser is safe — there's no server
 * render of this tree to mismatch. The main's margin animates as the rail hides.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* storage unavailable — the toggle still works for this session */
      }
      return next;
    });

  return (
    <>
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <CommandPalette />
      <NewProjectDialog />
      <main
        id="main"
        className={cn(
          "px-4 pb-10 pt-20 transition-[margin] duration-300 ease-out sm:px-6 md:pt-8 lg:px-10",
          collapsed ? "md:ml-0" : "md:ml-60",
        )}
      >
        {children}
      </main>
    </>
  );
}
