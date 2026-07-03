"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Check, X, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: "default" | "success" | "warning";
  /** Optional action, e.g. Undo. Clicking it dismisses the toast. */
  action?: { label: string; onClick: () => void };
  durationMs?: number;
}

interface ToastItem extends ToastInput {
  id: number;
  /** Playing its exit animation; removed from the list when it finishes. */
  leaving?: boolean;
}

const ToastContext = createContext<{ toast: (t: ToastInput) => void } | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx.toast;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    // exit choreography: mark it leaving, drop it once the animation played
    setItems((list) => list.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => {
      setItems((list) => list.filter((t) => t.id !== id));
    }, 190);
  }, []);

  const toast = useCallback(
    (input: ToastInput) => {
      const id = ++counter.current;
      setItems((list) => [...list.slice(-3), { ...input, id }]);
      const duration = input.durationMs ?? (input.action ? 6000 : 4000);
      window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* polite live region — announces without stealing focus */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-20 z-[90] flex flex-col items-center gap-2 px-4 md:bottom-6 md:items-end md:px-6"
      >
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border bg-surface-raised p-4 shadow-xl",
              item.leaving ? "animate-toast-out" : "animate-log-in",
              item.tone === "warning" ? "border-warning/40" : "border-border-strong",
            )}
          >
            {item.tone === "success" && (
              <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            )}
            {item.tone === "warning" && (
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{item.title}</p>
              {item.description && (
                <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">
                  {item.description}
                </p>
              )}
            </div>
            {item.action && (
              <button
                type="button"
                onClick={() => {
                  item.action?.onClick();
                  dismiss(item.id);
                }}
                className="-my-1 min-h-9 shrink-0 cursor-pointer rounded-md px-2.5 py-1 text-[13px] font-semibold text-primary hover:bg-primary-soft"
              >
                {item.action.label}
              </button>
            )}
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              aria-label="Dismiss notification"
              className="-my-1.5 -mr-1.5 flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-md text-faint hover:bg-muted hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
