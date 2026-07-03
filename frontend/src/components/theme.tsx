"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Theme state lives outside React (localStorage + the OS preference),
 * so it's modelled as an external store. `public/theme.js` applies the
 * class before first paint; this module keeps it in sync afterwards.
 */

const STORAGE_KEY = "clannon.theme";

export type Theme = "light" | "dark" | "system";

const listeners = new Set<() => void>();

function readTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
    return "light"; // brand default — crisp, readable warm paper
  } catch {
    return "light";
  }
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function readResolved(): "light" | "dark" {
  const theme = readTheme();
  if (theme === "system") return systemPrefersDark() ? "dark" : "light";
  return theme;
}

function applyClass() {
  document.documentElement.classList.toggle("dark", readResolved() === "dark");
}

export function setTheme(theme: Theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // storage unavailable — theme still applies for this page view
  }
  applyClass();
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const onSystemChange = () => {
    if (readTheme() === "system") {
      applyClass();
      notify();
    }
  };
  media.addEventListener("change", onSystemChange);
  return () => {
    listeners.delete(notify);
    media.removeEventListener("change", onSystemChange);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);
  const resolved = useSyncExternalStore(
    subscribe,
    readResolved,
    () => "light" as const,
  );
  return { theme, resolved, setTheme };
}

const META: Record<Theme, { icon: typeof Sun; label: string }> = {
  light: { icon: Sun, label: "Light theme" },
  dark: { icon: Moon, label: "Dark theme" },
  system: { icon: Monitor, label: "System theme" },
};

/**
 * light → dark → system → (opposite of what system resolves to), so
 * the first click always visibly changes the page.
 */
function nextTheme(theme: Theme, resolved: "light" | "dark"): Theme {
  if (theme === "system") return resolved === "dark" ? "light" : "dark";
  return theme === "light" ? "dark" : "system";
}

const SHORT_LABEL: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

/**
 * The explicit three-way control (Settings → Account). The header/sidebar
 * keep the compact cycling <ThemeToggle>; this is the labelled version
 * for when the user wants to *choose*, not cycle.
 */
export function ThemeSegment({ className }: { className?: string }) {
  const { theme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={cn(
        "inline-flex rounded-md border border-border bg-surface p-0.5",
        className,
      )}
    >
      {(["light", "dark", "system"] as Theme[]).map((value) => {
        const Icon = META[value].icon;
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(value)}
            className={cn(
              "flex cursor-pointer items-center gap-1.5 rounded-xs px-3 py-1.5 text-[13px] font-medium transition-colors",
              active
                ? "bg-primary-soft text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            {SHORT_LABEL[value]}
          </button>
        );
      })}
    </div>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, resolved } = useTheme();
  const { icon: Icon, label } = META[theme];
  const next = nextTheme(theme, resolved);

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`${label} — switch to ${next}`}
      title={`${label} (click for ${next})`}
      className={cn(
        "flex size-11 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors",
        "hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      <Icon className="size-[18px]" aria-hidden />
    </button>
  );
}
