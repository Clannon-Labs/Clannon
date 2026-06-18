"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useProjects } from "@/lib/api/hooks";
import type { Project } from "@/lib/api";

const STORAGE_KEY = "clannon.project";

function readStored(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

interface ProjectCtx {
  /** The user's stored pick — may be stale (deleted) or null (never chosen). */
  selectedProjectId: string | null;
  selectProject: (id: string) => void;
}

const Context = createContext<ProjectCtx | null>(null);

/**
 * Holds the "current project" selection. Client-side only (every scoped request
 * carries the projectId), persisted per browser. Mounts under RequireAuth, so
 * reading storage in the initializer is safe — there's no server render to
 * mismatch. See the Projects proposal in conversation/proposal.md.
 */
export function ProjectProvider({ children }: { children: ReactNode }) {
  const [selectedProjectId, setSelected] = useState<string | null>(readStored);

  const selectProject = (id: string) => {
    setSelected(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* storage unavailable — the choice still holds for this session */
    }
  };

  const value = useMemo(() => ({ selectedProjectId, selectProject }), [selectedProjectId]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

function useProjectCtx(): ProjectCtx {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useProjectCtx must be used within <ProjectProvider>");
  return ctx;
}

/** Sentinel for the "All projects" scope — see everything across projects. */
export const ALL_PROJECTS = "all";

export function useSelectProject() {
  return useProjectCtx().selectProject;
}

/** True when the user has explicitly chosen the "All projects" scope. */
export function useIsAllProjects(): boolean {
  return useProjectCtx().selectedProjectId === ALL_PROJECTS;
}

/**
 * The EFFECTIVE current project id used to scope requests. `undefined` means "no
 * filter" — i.e. All projects (explicitly chosen, or no projects exist yet).
 * Otherwise the stored pick if it's still real, else the most recent project.
 */
export function useCurrentProjectId(): string | undefined {
  const { selectedProjectId } = useProjectCtx();
  const { data: projects } = useProjects();
  return useMemo(() => {
    if (selectedProjectId === ALL_PROJECTS) return undefined; // explicit "all"
    if (!projects || projects.length === 0) return undefined;
    if (selectedProjectId && projects.some((p) => p.id === selectedProjectId)) {
      return selectedProjectId;
    }
    return projects[0].id; // default: the most recent project
  }, [projects, selectedProjectId]);
}

/** The effective current Project object — for display in the switcher. */
export function useCurrentProject(): Project | undefined {
  const id = useCurrentProjectId();
  const { data: projects } = useProjects();
  return useMemo(() => projects?.find((p) => p.id === id), [projects, id]);
}
