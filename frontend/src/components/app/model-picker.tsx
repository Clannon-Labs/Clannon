"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { Check, ChevronDown, ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { useModelConfig } from "@/lib/api/hooks";
import type { LayerModelConfig } from "@/lib/api";
import { useFocusTrap } from "@/lib/focus";
import { cn } from "@/lib/utils";

/* brand casing the naive title-case gets wrong ("gpt" → "Gpt") — applied per
   token; anything unmapped keeps the plain title-case treatment */
const BRAND_CASING: Record<string, string> = {
  gpt: "GPT",
  glm: "GLM",
};

/** A friendlier display name for a model id — "gemini-2.5-flash" → "Gemini 2.5
 *  Flash", "claude-opus-4-8" → "Claude Opus 4.8", "gpt-5.5" → "GPT-5.5" (OpenAI
 *  hyphenates its brand; the others don't). Display only; the raw id is always
 *  what gets sent. */
export function prettyModel(id: string): string {
  return id
    .split("-")
    .filter((p) => !/^\d{5,}$/.test(p)) // drop date-like groups (e.g. 20251001)
    .map((p) =>
      BRAND_CASING[p] ?? (/^\d/.test(p) ? p : p.charAt(0).toUpperCase() + p.slice(1)),
    )
    .join(" ")
    .replace(/(\b\d) (\d\b)/g, "$1.$2") // "4 8" → "4.8"
    .replace(/^GPT (?=\d)/, "GPT-"); // brand hyphen: "GPT 5.5" → "GPT-5.5"
}

/** Provider grouping for model lists — a flat wall of 16 ids reads like an
 *  unstyled <select>. Order: the recommended model's provider first, then by
 *  first appearance. Recommended is pinned to the top of its group. */
const PROVIDERS: [RegExp, string][] = [
  [/^claude/i, "Anthropic"],
  [/^gemini/i, "Google"],
  [/^(gpt|o\d)/i, "OpenAI"],
  [/^glm/i, "Zhipu"],
];
function providerOf(id: string): string {
  for (const [re, name] of PROVIDERS) if (re.test(id)) return name;
  return "Other";
}
export function groupModelOptions(
  options: string[],
  recommended?: string,
): { provider: string; options: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const opt of options) {
    const key = providerOf(opt);
    if (!groups.has(key)) groups.set(key, []);
    if (opt === recommended) groups.get(key)!.unshift(opt);
    else groups.get(key)!.push(opt);
  }
  const order = [...groups.keys()];
  if (recommended) {
    const first = providerOf(recommended);
    order.sort((a, b) => (a === first ? -1 : b === first ? 1 : 0));
  }
  return order.map((provider) => ({ provider, options: groups.get(provider)! }));
}

/** The quiet taxonomy row above each provider's models. Presentation-only —
 *  it must not register as an option in the listbox. */
function ProviderLabel({ name }: { name: string }) {
  return (
    <li role="presentation" aria-hidden className="px-3 pb-0.5 pt-2 first:pt-1">
      <span className="tag-label text-faint">{name}</span>
    </li>
  );
}

/**
 * A themed model dropdown for the Settings page — a real menu in OUR styling,
 * not a native <select> (whose option list can't be themed). Expands in place.
 */
function ModelDropdown({
  value,
  options,
  onChange,
  disabled,
  label,
  recommended,
}: {
  value: string;
  options: string[];
  onChange: (model: string) => void;
  disabled?: boolean;
  label: string;
  /** The role's default — pinned first in its provider group. */
  recommended?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  return (
    <div ref={ref} className="relative sm:min-w-[13rem]">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model for ${label}`}
        className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-[13px] text-foreground transition-colors hover:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 disabled:opacity-50"
      >
        {/* display name up front; the raw id lives in the title for the curious */}
        <span className="truncate" title={value}>{prettyModel(value)}</span>
        <ChevronDown
          className={cn("size-3.5 shrink-0 text-faint transition-transform duration-200", open && "rotate-180")}
          aria-hidden
        />
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 flex max-h-64 w-full flex-col gap-0.5 overflow-y-auto rounded-md border border-border bg-surface-raised p-1 shadow-lg"
        >
          {groupModelOptions(options, recommended).map((group) => [
            <ProviderLabel key={`h-${group.provider}`} name={group.provider} />,
            ...group.options.map((option) => {
            const selected = option === value;
            return (
              <li key={option}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    onChange(option);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-[13px] transition-colors",
                    selected ? "bg-primary-soft text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <span className="truncate" title={option}>{prettyModel(option)}</span>
                  {selected && <Check className="size-3.5 shrink-0" aria-hidden />}
                </button>
              </li>
            );
            }),
          ])}
        </ul>
      )}
    </div>
  );
}

/**
 * The Settings → Models list: one bordered card, roles as divided rows. Renders
 * whatever roles the backend sends; locked roles (verifier, filter) show
 * read-only.
 */
export function ModelRoleList({
  layers,
  valueFor,
  onSelect,
  pending = false,
  includeLocked = true,
}: {
  layers: LayerModelConfig[];
  valueFor: (layer: LayerModelConfig) => string;
  onSelect: (layer: LayerModelConfig, model: string) => void;
  pending?: boolean;
  includeLocked?: boolean;
}) {
  const shown = includeLocked ? layers : layers.filter((l) => !l.locked);
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
      {shown.map((layer) => (
        <li
          key={layer.layer}
          className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
        >
          <div className="min-w-0 sm:flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {/* only the locked rows carry an icon — five identical glyphs in a
                  row is decoration, one meaningful shield is information */}
              {layer.locked && (
                <ShieldCheck className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              )}
              {layer.label}
              {layer.locked && (
                // neutral, not amber: this is system status, and amber is memory's
                <span className="tag-label rounded-full border border-border bg-muted px-2 py-0.5 text-muted-foreground">
                  System managed
                </span>
              )}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{layer.description}</p>
            {/* say "Recommended" only when the row is NOT already on it —
                otherwise the page repeats itself three times per row */}
            {layer.default && !layer.locked && valueFor(layer) !== layer.default && (
              <p className="mt-1 text-[12px] text-faint">
                Recommended: <span title={layer.default}>{prettyModel(layer.default)}</span>
              </p>
            )}
          </div>

          <div className="shrink-0">
            {layer.locked ? (
              <span
                title={layer.model}
                className="inline-flex h-10 items-center rounded-md border border-border bg-background px-3 text-[13px] text-muted-foreground"
              >
                {prettyModel(layer.model)}
              </span>
            ) : (
              <ModelDropdown
                value={valueFor(layer)}
                options={layer.options}
                onChange={(m) => onSelect(layer, m)}
                disabled={pending}
                label={layer.label}
                recommended={layer.default}
              />
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

const SESSION_MODELS_KEY = "clannon.session.models";

function readSessionModels(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(SESSION_MODELS_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

/**
 * The model choice for the conversation — a sparse { role: modelId } sent with each
 * run. Persisted per browser so it carries across turns (the model you pick is the
 * default for the whole session, not one run). `setAll` sets every applicable role
 * at once (the common case: one model for the orchestrator AND every expert);
 * `setRole` is the per-expert override. Lives behind RequireAuth, so reading storage
 * in the initializer is safe.
 */
export function useSessionModels() {
  const [models, setModels] = useState<Record<string, string>>(readSessionModels);

  const update = (fn: (m: Record<string, string>) => Record<string, string>) =>
    setModels((m) => {
      const next = fn(m);
      try {
        localStorage.setItem(SESSION_MODELS_KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable — the choice still holds in memory */
      }
      return next;
    });

  return {
    models,
    count: Object.keys(models).length,
    /** Override a single role (per-expert advanced control). */
    setRole: (layer: LayerModelConfig, model: string) =>
      update((m) => {
        const next = { ...m };
        if (layer.default && model === layer.default) delete next[layer.layer];
        else next[layer.layer] = model;
        return next;
      }),
    /** One model for the whole conversation: set every non-locked role that can run
     *  it, and clear any per-expert overrides. Roles that can't (e.g. a vision-only
     *  media expert) keep their own model. */
    setAll: (layers: LayerModelConfig[], model: string) =>
      update(() => {
        const next: Record<string, string> = {};
        for (const l of layers) {
          if (l.locked || !l.options.includes(model)) continue;
          next[l.layer] = model;
        }
        return next;
      }),
    reset: () => update(() => ({})),
  };
}

/**
 * The composer's per-run model control. The trigger is seamless text showing the
 * orchestrator's model + a chevron; clicking opens a menu that drills from the
 * roles (orchestrator, experts…) into each role's model list — a real, themed
 * menu, not a boxy native select. Choices ride on the run POST (this run only).
 */
export function SessionModelPicker({
  models,
  onSetRole,
  onSetAll,
}: {
  models: Record<string, string>;
  onSetRole: (layer: LayerModelConfig, model: string) => void;
  onSetAll: (layers: LayerModelConfig[], model: string) => void;
}) {
  const { data: layers } = useModelConfig();
  // fixed popover anchored to the trigger, so the composer's overflow-hidden box
  // can't clip it. It opens toward whichever side has more room (`up`), and
  // `view`/`dir` drive the drill-in from the role list into one role's models.
  const [anchor, setAnchor] = useState<{
    right: number;
    top?: number;
    bottom?: number;
    up: boolean;
    maxH: number;
  } | null>(null);
  const [view, setView] = useState<string>("main"); // "main" | "experts" | a layer key
  const [dir, setDir] = useState(1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!anchor) return;
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (popRef.current?.contains(t) || triggerRef.current?.contains(t)) return;
      setAnchor(null);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setAnchor(null);
    // close when the PAGE scrolls (the fixed popover would detach) — but not when
    // the menu's own list scrolls
    const onScroll = (e: Event) => {
      if (popRef.current?.contains(e.target as Node)) return;
      setAnchor(null);
    };
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { capture: true });
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, { capture: true });
    };
  }, [anchor]);

  // keyboard: focus moves into the dialog on open, Tab cycles inside, and
  // closing (Escape / pick / outside click) hands focus back to the trigger
  useFocusTrap(anchor !== null, popRef);

  // drilling between views swaps the whole panel content — land focus on the
  // new view's first control so the keyboard follows the drill (DOM focus
  // only; no state changes here)
  useEffect(() => {
    if (!anchor) return;
    popRef.current?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
  }, [view, anchor]);

  if (!layers) return null;

  const roles = layers.filter((l) => !l.locked);
  const orchestrator = roles.find((l) => l.layer === "orchestrator") ?? roles[0];
  if (!orchestrator) return null;
  const valueFor = (l: LayerModelConfig) => models[l.layer] ?? l.model;
  const overrides = Object.keys(models).length;
  const experts = roles.filter((l) => l.layer !== orchestrator.layer);
  const current = roles.find((l) => l.layer === view); // a role's options view
  const parentOf = (role: LayerModelConfig) => (role.layer === orchestrator.layer ? "main" : "experts");

  const goTo = (v: string) => {
    setDir(1);
    setView(v);
  };
  const back = (target = "main") => {
    setDir(-1);
    setView(target);
  };

  function toggle() {
    if (anchor) {
      setAnchor(null);
      return;
    }
    const r = triggerRef.current?.getBoundingClientRect();
    if (!r) return;
    setView("main");
    setDir(1);
    // prefer opening UP (right above the arrow); fall back to down only if there
    // genuinely isn't room. Either way cap the height to the gap so it can't clip.
    // Use the layout viewport (clientWidth/Height) — it excludes the scrollbar, so
    // a page with a scrollbar (a run thread) doesn't shift the menu left.
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    const above = r.top - 8;
    const below = vh - r.bottom - 8;
    const up = above >= 220 || above >= below;
    setAnchor({
      right: vw - r.right,
      up,
      maxH: Math.max(150, (up ? above : below) - 8),
      ...(up ? { bottom: vh - r.top + 8 } : { top: r.bottom + 8 }),
    });
  }

  // cap the scrolling list so the whole menu fits in the gap — room minus the
  // chrome around it. The main view carries more chrome (header + customize
  // row + two-line caption); under-reserving guillotines the caption (§11.4).
  const listMaxH = anchor ? Math.max(120, anchor.maxH - (view === "main" ? 150 : 104)) : 280;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={anchor !== null}
        title="Models for this run"
        className="flex min-w-0 max-w-[9.5rem] shrink cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:max-w-[15rem]"
      >
        <span className="truncate">{prettyModel(valueFor(orchestrator))}</span>
        {overrides > 0 && <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />}
        <ChevronDown
          className={cn("size-3.5 shrink-0 text-faint transition-transform duration-200", anchor && "rotate-180")}
          aria-hidden
        />
      </button>

      {anchor &&
        createPortal(
          <motion.div
            ref={popRef}
            role="dialog"
            aria-label="Models for this run"
          initial={{ opacity: 0, scale: 0.96, y: anchor.up ? 6 : -6 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: "fixed",
            right: anchor.right,
            top: anchor.top,
            bottom: anchor.bottom,
            maxHeight: anchor.maxH,
            transformOrigin: anchor.up ? "bottom right" : "top right",
          }}
          className="z-50 flex w-[min(19rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-border bg-surface-raised p-1.5 shadow-2xl"
        >
          <motion.div
            key={view}
            initial={{ opacity: 0, x: dir > 0 ? 16 : -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            {view === "main" ? (
              // one model for the WHOLE conversation — picking sets every role that
              // can run it (orchestrator + experts). Per-expert overrides live behind
              // "Customize by expert".
              <div className="flex flex-col">
                <p className="px-3 pb-1 pt-2 tag-label text-faint">Model for this conversation</p>
                <ul
                  role="listbox"
                  aria-label="Conversation model"
                  className="overflow-y-auto overscroll-contain"
                  style={{ maxHeight: listMaxH }}
                >
                  {groupModelOptions(orchestrator.options, orchestrator.default).map((group) => [
                    <ProviderLabel key={`h-${group.provider}`} name={group.provider} />,
                    ...group.options.map((opt) => {
                    const selected = valueFor(orchestrator) === opt;
                    return (
                      <li key={opt}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={selected}
                          onClick={() => {
                            onSetAll(layers, opt);
                            setAnchor(null);
                          }}
                          className={cn(
                            "flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition-colors",
                            selected ? "bg-primary-soft" : "hover:bg-muted",
                          )}
                        >
                          <span className="min-w-0">
                            <span className={cn("block truncate text-[13px]", selected ? "font-medium text-primary" : "text-foreground")}>
                              {prettyModel(opt)}
                            </span>
                            {orchestrator.default === opt && (
                              <span className="block text-[11px] text-faint">Recommended</span>
                            )}
                          </span>
                          {selected && <Check className="size-4 shrink-0 text-primary" aria-hidden />}
                        </button>
                      </li>
                    );
                    }),
                  ])}
                </ul>
                {experts.length > 0 && (
                  <>
                    <div className="mx-2 my-1 h-px bg-border" />
                    <button
                      type="button"
                      onClick={() => goTo("experts")}
                      className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted"
                    >
                      <span className="text-sm font-medium text-foreground">Customize by expert</span>
                      <span className="flex items-center gap-1 text-[12px] text-faint">
                        advanced
                        <ChevronRight className="size-4 shrink-0" aria-hidden />
                      </span>
                    </button>
                  </>
                )}
                <p className="px-3 pb-1 pt-1.5 text-[11px] leading-relaxed text-faint">
                  Applies to the orchestrator and every expert that can run it, for this whole
                  conversation.
                </p>
              </div>
            ) : view === "experts" ? (
              // pick which specialist to set a model for
              <div className="flex flex-col">
                <button
                  type="button"
                  onClick={() => back("main")}
                  className="flex items-center gap-1 rounded-lg px-2 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
                >
                  <ChevronLeft className="size-4 shrink-0 text-faint" aria-hidden />
                  More models
                </button>
                <p className="px-3 pb-1 text-[12px] leading-relaxed text-faint">
                  The specialists the orchestrator can spawn — pick one to set its model.
                </p>
                <div className="mx-1 mb-1 h-px bg-border" />
                <div className="overflow-y-auto overscroll-contain" style={{ maxHeight: listMaxH }}>
                  {experts.map((role) => (
                    <button
                      key={role.layer}
                      type="button"
                      onClick={() => goTo(role.layer)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted"
                    >
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium text-foreground">{role.label}</span>
                        <span className="block truncate text-[12px] text-muted-foreground">
                          {prettyModel(valueFor(role))}
                        </span>
                      </span>
                      <ChevronRight className="size-4 shrink-0 text-faint" aria-hidden />
                    </button>
                  ))}
                </div>
              </div>
            ) : current ? (
              // a role's model options (the orchestrator or one expert)
              <div className="flex flex-col">
                <button
                  type="button"
                  onClick={() => back(parentOf(current))}
                  className="flex items-center gap-1 rounded-lg px-2 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
                >
                  <ChevronLeft className="size-4 shrink-0 text-faint" aria-hidden />
                  {current.label}
                </button>
                {current.description && (
                  <p className="px-3 pb-1 text-[12px] leading-relaxed text-faint">{current.description}</p>
                )}
                <div className="mx-1 mb-1 h-px bg-border" />
                <ul
                  className="overflow-y-auto overscroll-contain"
                  style={{ maxHeight: listMaxH }}
                  role="listbox"
                  aria-label={`${current.label} model`}
                >
                  {groupModelOptions(current.options, current.default).map((group) => [
                    <ProviderLabel key={`h-${group.provider}`} name={group.provider} />,
                    ...group.options.map((opt) => {
                    const selected = valueFor(current) === opt;
                    return (
                      <li key={opt}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={selected}
                          onClick={() => {
                            onSetRole(current, opt);
                            back(parentOf(current));
                          }}
                          className={cn(
                            "flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition-colors",
                            selected ? "bg-primary-soft" : "hover:bg-muted",
                          )}
                        >
                          <span className="min-w-0">
                            <span className={cn("block truncate text-[13px]", selected ? "font-medium text-primary" : "text-foreground")}>
                              {prettyModel(opt)}
                            </span>
                            {current.default === opt && (
                              <span className="block text-[11px] text-faint">Recommended</span>
                            )}
                          </span>
                          {selected && <Check className="size-4 shrink-0 text-primary" aria-hidden />}
                        </button>
                      </li>
                    );
                    }),
                  ])}
                </ul>
              </div>
            ) : null}
          </motion.div>
          </motion.div>,
          document.body,
        )}
    </>
  );
}
