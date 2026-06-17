"use client";

import { useState } from "react";
import { Cpu, ShieldCheck, ChevronDown, ChevronRight } from "lucide-react";
import { useModelConfig } from "@/lib/api/hooks";
import type { LayerModelConfig } from "@/lib/api";
import { cn } from "@/lib/utils";

/** A model `<select>` styled as a clean dropdown button — the native arrow is
 *  removed (appearance-none) and replaced with a consistent chevron, so it looks
 *  the same in every browser. Still a real select: keyboard + mobile friendly. */
function ModelSelect({
  layer,
  value,
  onSelect,
  pending,
  compact,
}: {
  layer: LayerModelConfig;
  value: string;
  onSelect: (layer: LayerModelConfig, model: string) => void;
  pending?: boolean;
  compact?: boolean;
}) {
  return (
    <div className="relative">
      <label className="sr-only" htmlFor={`model-${layer.layer}`}>
        Model for {layer.label}
      </label>
      <select
        id={`model-${layer.layer}`}
        value={value}
        disabled={pending}
        onChange={(e) => onSelect(layer, e.target.value)}
        className={cn(
          "w-full cursor-pointer appearance-none rounded-md border border-border-strong bg-surface-raised font-mono text-foreground transition-colors hover:border-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 disabled:opacity-50",
          compact ? "h-9 pl-2.5 pr-8 text-base sm:text-[12.5px]" : "h-10 pl-3 pr-9 text-base sm:min-w-[13rem] sm:text-[13px]",
        )}
      >
        {layer.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <ChevronDown
        className={cn(
          "pointer-events-none absolute top-1/2 -translate-y-1/2 text-faint",
          compact ? "right-2 size-3.5" : "right-2.5 size-4",
        )}
        aria-hidden
      />
    </div>
  );
}

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

  // composer: a tight stack of rows
  if (compact) {
    return (
      <div className="flex flex-col gap-1">
        {shown.map((layer) => (
          <div
            key={layer.layer}
            className="flex items-center justify-between gap-3 rounded-md bg-background px-3 py-1.5"
          >
            <p className="flex min-w-0 items-center gap-2 text-[13px] font-medium">
              {layer.locked ? (
                <ShieldCheck className="size-3.5 shrink-0 text-memory" aria-hidden />
              ) : (
                <Cpu className="size-3.5 shrink-0 text-primary" aria-hidden />
              )}
              <span className="truncate">{layer.label}</span>
            </p>
            {layer.locked ? (
              <span className="shrink-0 rounded-md border border-border bg-surface px-2 py-1 font-mono text-[12px] text-muted-foreground">
                {layer.model}
              </span>
            ) : (
              <ModelSelect layer={layer} value={valueFor(layer)} onSelect={onSelect} pending={pending} compact />
            )}
          </div>
        ))}
      </div>
    );
  }

  // settings: one bordered card, roles as divided rows (a clean settings list)
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
      {shown.map((layer) => (
        <li
          key={layer.layer}
          className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
        >
          <div className="min-w-0 sm:flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {layer.locked ? (
                <ShieldCheck className="size-4 shrink-0 text-memory" aria-hidden />
              ) : (
                <Cpu className="size-4 shrink-0 text-primary" aria-hidden />
              )}
              {layer.label}
              {layer.locked && (
                <span className="tag-label rounded-full bg-memory-soft px-2 py-0.5 text-memory">
                  System managed
                </span>
              )}
            </p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{layer.description}</p>
            {layer.default && !layer.locked && (
              <p className="mt-1 text-[11.5px] text-faint">
                Recommended: <span className="font-mono">{layer.default}</span>
              </p>
            )}
          </div>

          <div className="shrink-0">
            {layer.locked ? (
              <span className="inline-flex h-10 items-center rounded-md border border-border bg-background px-3 font-mono text-[13px] text-muted-foreground">
                {layer.model}
              </span>
            ) : (
              <ModelSelect layer={layer} value={valueFor(layer)} onSelect={onSelect} pending={pending} />
            )}
          </div>
        </li>
      ))}
    </ul>
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
