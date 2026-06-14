"use client";

import { useState } from "react";
import { Cpu, ShieldCheck, ChevronRight } from "lucide-react";
import { useModelConfig } from "@/lib/api/hooks";
import type { LayerModelConfig } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The per-role model list, shared by Settings (workspace defaults) and the
 * composer (per-session overrides) — one control, two sinks. It renders whatever
 * roles the backend sends, so a new role appears with no code change; locked
 * roles (verifier, filter) show read-only.
 */
export function ModelRoleList({
  layers,
  valueFor,
  onSelect,
  pending = false,
  compact = false,
  includeLocked = true,
}: {
  layers: LayerModelConfig[];
  valueFor: (layer: LayerModelConfig) => string;
  onSelect: (layer: LayerModelConfig, model: string) => void;
  pending?: boolean;
  compact?: boolean;
  includeLocked?: boolean;
}) {
  const shown = includeLocked ? layers : layers.filter((l) => !l.locked);
  return (
    <div className={cn("flex flex-col", compact ? "gap-1.5" : "gap-3")}>
      {shown.map((layer) => (
        <div
          key={layer.layer}
          className={cn(
            compact ? "rounded-md bg-background px-3 py-2" : "rounded-lg border border-border bg-surface p-5",
          )}
        >
          <div
            className={cn(
              "flex gap-3",
              compact ? "items-center justify-between" : "flex-col sm:flex-row sm:items-center sm:justify-between",
            )}
          >
            <div className="min-w-0">
              <p className={cn("flex items-center gap-2 font-semibold", compact ? "text-[13px]" : "text-[15px]")}>
                {layer.locked ? (
                  <ShieldCheck className="size-4 shrink-0 text-memory" aria-hidden />
                ) : (
                  <Cpu className="size-4 shrink-0 text-primary" aria-hidden />
                )}
                {layer.label}
                {layer.locked && !compact && (
                  <span className="tag-label rounded-full bg-memory-soft px-2 py-0.5 text-memory">
                    System managed
                  </span>
                )}
              </p>
              {!compact && (
                <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{layer.description}</p>
              )}
              {!compact && layer.default && (
                <p className="mt-1 text-[12px] text-faint">
                  Best for this role: <span className="font-mono">{layer.default}</span>
                </p>
              )}
            </div>

            {layer.locked ? (
              <p
                className={cn(
                  "shrink-0 rounded-md border border-border bg-background font-mono text-muted-foreground",
                  compact ? "px-2 py-1 text-[12px]" : "px-3 py-2.5 text-[13px]",
                )}
              >
                {layer.model}
              </p>
            ) : (
              <div className="shrink-0">
                <label className="sr-only" htmlFor={`model-${layer.layer}`}>
                  Model for {layer.label}
                </label>
                <select
                  id={`model-${layer.layer}`}
                  value={valueFor(layer)}
                  disabled={pending}
                  onChange={(e) => onSelect(layer, e.target.value)}
                  className={cn(
                    "cursor-pointer rounded-md border border-border-strong bg-surface-raised font-mono text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25",
                    compact ? "h-9 px-2.5 text-base sm:text-[12.5px]" : "h-10 px-3 text-base sm:text-[13px]",
                  )}
                >
                  {layer.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Per-session model overrides — a sparse { role: modelId }. Setting a role back to
 *  its backend default drops the override, so we only ever send real changes. */
export function useSessionModels() {
  const [models, setModels] = useState<Record<string, string>>({});
  return {
    models,
    count: Object.keys(models).length,
    setRole: (layer: LayerModelConfig, model: string) =>
      setModels((m) => {
        const next = { ...m };
        if (layer.default && model === layer.default) delete next[layer.layer];
        else next[layer.layer] = model;
        return next;
      }),
    reset: () => setModels({}),
  };
}

/**
 * A collapsible per-session model picker for the composers. Choices go into the
 * `models` form field on the run POST (this run only); default-collapsed so it
 * never clutters the composer.
 */
export function SessionModelPicker({
  models,
  onSetRole,
}: {
  models: Record<string, string>;
  onSetRole: (layer: LayerModelConfig, model: string) => void;
}) {
  const { data: layers } = useModelConfig();
  const [open, setOpen] = useState(false);
  if (!layers) return null;
  const count = Object.keys(models).length;
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex min-h-9 cursor-pointer items-center gap-2 text-[12.5px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronRight
          className={cn("size-3.5 shrink-0 text-faint transition-transform duration-200", open && "rotate-90")}
          aria-hidden
        />
        <Cpu className="size-3.5 shrink-0" aria-hidden />
        Models
        <span className="font-normal text-faint">
          {count > 0 ? `· ${count} set for this run` : "· workspace defaults"}
        </span>
      </button>
      {open && (
        <div className="mt-2">
          <ModelRoleList
            layers={layers}
            includeLocked={false}
            compact
            valueFor={(l) => models[l.layer] ?? l.model}
            onSelect={onSetRole}
          />
          <p className="mt-2 px-1 text-[11.5px] text-faint">
            Applies to this run only. Set your standing defaults in Settings → Models.
          </p>
        </div>
      )}
    </div>
  );
}
