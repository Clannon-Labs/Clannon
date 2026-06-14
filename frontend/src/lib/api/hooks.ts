"use client";

import { useEffect, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { getClient } from "./index";
import { PLANS, planById, type Plan, type PlanId } from "@/config/plans";
import type {
  DecisionLogEntry,
  ExpertState,
  MemoryEntry,
  Run,
  RunStatus,
  Source,
  User,
} from "./types";

export const queryKeys = {
  remoteConfig: ["remote-config"] as const,
  me: ["me"] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  memory: ["memory"] as const,
  usage: ["usage"] as const,
  models: ["models"] as const,
};

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: () => getClient().me() });
}

/**
 * The backend's read-only /config payload. Fetched once per session;
 * null (backend silent) means local defaults apply everywhere.
 */
export function useRemoteConfig() {
  return useQuery({
    queryKey: queryKeys.remoteConfig,
    queryFn: () => getClient().getRemoteConfig(),
    staleTime: Infinity,
    retry: false,
  });
}

/** Plans as the backend defines them, falling back to plans.ts. */
export function useEffectivePlans(): Plan[] {
  const { data } = useRemoteConfig();
  return data?.plans?.length ? data.plans : PLANS;
}

export function useEffectivePlan(id: PlanId | undefined): Plan | undefined {
  const plans = useEffectivePlans();
  return id ? (plans.find((p) => p.id === id) ?? planById(id)) : undefined;
}

export function useRuns() {
  return useQuery({ queryKey: queryKeys.runs, queryFn: () => getClient().listRuns() });
}

export function useRun(id: string) {
  return useQuery({ queryKey: queryKeys.run(id), queryFn: () => getClient().getRun(id) });
}

/** Prior turns of this run's session (the conversation so far). */
export function useRunThread(id: string) {
  return useQuery({
    queryKey: ["runs", id, "thread"],
    queryFn: () => getClient().getRunThread(id),
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { brief: string; files?: File[] }) =>
      getClient().createRun(vars.brief, vars.files),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.runs }),
  });
}

/** Fetch a run artifact's bytes (auth via cookie). The caller saves the Blob. */
export function useDownloadArtifact() {
  return useMutation({
    mutationFn: ({ runId, name }: { runId: string; name: string }) =>
      getClient().downloadArtifact(runId, name),
  });
}

export function useSetRunFeedback(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { rating: "up" | "down" | null; comment?: string }) =>
      getClient().setRunFeedback(runId, vars.rating, vars.comment),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.run(runId) }),
  });
}

export function useCreateFollowUp(parentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (brief: string) => getClient().createFollowUp(parentId, brief),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.runs });
      qc.invalidateQueries({ queryKey: ["runs", parentId, "thread"] });
    },
  });
}

export function useMemoryEntries() {
  return useQuery({ queryKey: queryKeys.memory, queryFn: () => getClient().listMemory() });
}

export function useSaveMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string }) =>
      getClient().saveMemoryEntry(entry),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.memory }),
  });
}

export function useUploadMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => getClient().uploadMemoryFiles(files),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.memory }),
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => getClient().deleteMemoryEntry(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.memory }),
  });
}

export function useUsage() {
  return useQuery({ queryKey: queryKeys.usage, queryFn: () => getClient().getUsage() });
}

export function useModelConfig() {
  return useQuery({ queryKey: queryKeys.models, queryFn: () => getClient().getModelConfig() });
}

export function useSetModelLayer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ layer, model }: { layer: string; model: string }) =>
      getClient().setModelLayer(layer, model),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.models }),
  });
}

export function useStartCheckout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: PlanId) => getClient().startCheckout(planId),
    onSuccess: (res) => {
      if (res.url) {
        // real backend: hand the browser to Stripe Checkout
        window.location.assign(res.url);
        return;
      }
      // mock: plan changed in place
      qc.invalidateQueries({ queryKey: queryKeys.me });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => getClient().logout(),
    onSuccess: () => qc.setQueryData<User | null>(queryKeys.me, null),
  });
}

/* ------------------------------------------------------------------
   Live run state — subscribes to the event stream and folds events
   into one renderable structure.
------------------------------------------------------------------- */

export interface LiveRunState {
  status: RunStatus;
  log: DecisionLogEntry[];
  experts: ExpertState[];
  sources: Source[];
  reportText: string;
  reportDone: boolean;
  tokensUsed: number;
  streamError: string | null;
  live: boolean;
}

const TERMINAL: RunStatus[] = ["delivered", "blocked", "failed"];

const initialLiveState = (): LiveRunState => ({
  status: "queued",
  log: [],
  experts: [],
  sources: [],
  reportText: "",
  reportDone: false,
  tokensUsed: 0,
  streamError: null,
  live: false,
});

export function useLiveRun(run: Run | undefined): LiveRunState {
  // Only what the stream itself produced lives in state; everything
  // the run query already knows is merged during render below.
  const [state, setState] = useState<LiveRunState>(initialLiveState);
  const qc = useQueryClient();
  const startedFor = useRef<string | null>(null);
  // Which run.id `state` currently holds. The RunPage component is reused
  // across /runs/[id] navigations, so without this the previous run's
  // streamed log/report would bleed into the next run through the merge below.
  const stateRunId = useRef<string | null>(null);

  useEffect(() => {
    if (!run) return;

    // A different run is on screen now — drop the prior run's streamed state
    // before it can show through the merge. Done for ANY target, including a
    // terminal one (e.g. opening a delivered prior turn while a stream is live).
    if (stateRunId.current !== run.id) {
      stateRunId.current = run.id;
      setState(initialLiveState());
    }

    if (TERMINAL.includes(run.status)) return;
    if (startedFor.current === run.id) return;
    startedFor.current = run.id;

    const controller = new AbortController();

    (async () => {
      setState((s) => ({ ...s, live: true }));
      try {
        for await (const event of getClient().streamRun(run.id, controller.signal)) {
          setState((s) => {
            switch (event.type) {
              case "status":
                return { ...s, status: event.status };
              case "log":
                return { ...s, log: [...s.log, event.entry] };
              case "expert": {
                const idx = s.experts.findIndex((e) => e.id === event.expert.id);
                const experts =
                  idx >= 0
                    ? s.experts.map((e, i) => (i === idx ? event.expert : e))
                    : [...s.experts, event.expert];
                return { ...s, experts };
              }
              case "sources":
                return { ...s, sources: event.sources };
              case "report_delta":
                return { ...s, reportText: s.reportText + event.text };
              case "report_done":
                return { ...s, reportDone: true };
              case "usage":
                return { ...s, tokensUsed: event.tokensUsed };
            }
          });
        }
        setState((s) => ({ ...s, live: false }));
        qc.invalidateQueries({ queryKey: queryKeys.run(run.id) });
        qc.invalidateQueries({ queryKey: queryKeys.runs });
        qc.invalidateQueries({ queryKey: queryKeys.memory });
        qc.invalidateQueries({ queryKey: queryKeys.usage });
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setState((s) => ({
            ...s,
            live: false,
            streamError: "The live stream dropped. Refresh to reconnect.",
          }));
        }
      }
    })();

    return () => controller.abort();
  }, [run, qc]);

  if (!run) return state;

  // merge: streamed events win where present, the fetched run fills
  // in the rest (covers completed runs and page refreshes)
  return {
    ...state,
    status: state.status !== "queued" ? state.status : run.status,
    log: state.log.length ? state.log : run.decisionLog,
    experts: state.experts.length ? state.experts : run.experts,
    sources: state.sources.length ? state.sources : run.sources,
    reportText: state.reportText || run.report || "",
    reportDone: state.reportDone || Boolean(run.report),
    tokensUsed: Math.max(state.tokensUsed, run.tokensUsed),
  };
}
