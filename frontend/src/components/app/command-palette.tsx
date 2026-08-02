"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutGrid,
  Target,
  Settings,
  Cpu,
  BarChart3,
  CreditCard,
  History,
  PenLine,
  Sun,
  Moon,
  Monitor,
  LogOut,
  FileText,
  Search,
  type LucideIcon,
} from "lucide-react";
import { useLogout, useRuns } from "@/lib/api/hooks";
import { setTheme } from "@/components/theme";
import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  hint?: string;
  keywords: string;
  icon: LucideIcon;
  group: string;
  run: () => void;
}

/** Event any component can dispatch to toggle the command palette — cleaner than
 *  synthesizing a fake ⌘K keystroke, and the only way in on touch (no keyboard). */
export const COMMAND_PALETTE_EVENT = "clannon:command-palette";

/** Open (toggle) the command palette from anywhere — e.g. a tap target. */
export function openCommandPalette() {
  window.dispatchEvent(new Event(COMMAND_PALETTE_EVENT));
}

export function CommandPalette() {
  const router = useRouter();
  const logout = useLogout();
  const { data: runs } = useRuns();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // global shortcut (⌘/Ctrl-K) + the toggle event used by on-screen triggers
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onToggle = () => setOpen((o) => !o);
    window.addEventListener("keydown", onKey);
    window.addEventListener(COMMAND_PALETTE_EVENT, onToggle);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(COMMAND_PALETTE_EVENT, onToggle);
    };
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      setQuery("");
      setSelected(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => () => {
      setOpen(false);
      router.push(path);
    };
    const base: Command[] = [
      { id: "new", label: "New research", hint: "start a brief", keywords: "run brief create research start", icon: PenLine, group: "Actions", run: go("/app") },
      { id: "ws", label: "Workspace", keywords: "home runs workspace", icon: LayoutGrid, group: "Go to", run: go("/app") },
      { id: "mem", label: "Memory", keywords: "archive wiki semantic episodic procedural", icon: Target, group: "Go to", run: go("/app/memory") },
      { id: "history", label: "History", keywords: "history past runs search filter conversations", icon: History, group: "Go to", run: go("/app/history") },
      { id: "set", label: "Settings — Account", keywords: "settings account profile", icon: Settings, group: "Go to", run: go("/app/settings?tab=account") },
      { id: "models", label: "Settings — Models", keywords: "settings models llm layers configure", icon: Cpu, group: "Go to", run: go("/app/settings?tab=models") },
      { id: "usage", label: "Settings — Usage", keywords: "settings usage tokens budget spend", icon: BarChart3, group: "Go to", run: go("/app/settings?tab=usage") },
      { id: "billing", label: "Settings — Billing", keywords: "settings billing plan subscription upgrade", icon: CreditCard, group: "Go to", run: go("/app/settings?tab=billing") },
      { id: "t-light", label: "Theme: light", keywords: "theme light paper", icon: Sun, group: "Theme", run: () => { setTheme("light"); setOpen(false); } },
      { id: "t-dark", label: "Theme: dark", keywords: "theme dark night", icon: Moon, group: "Theme", run: () => { setTheme("dark"); setOpen(false); } },
      { id: "t-system", label: "Theme: system", keywords: "theme system auto os", icon: Monitor, group: "Theme", run: () => { setTheme("system"); setOpen(false); } },
      {
        id: "signout",
        label: "Sign out",
        keywords: "logout sign out exit",
        icon: LogOut,
        group: "Account",
        run: () => {
          setOpen(false);
          logout.mutate(undefined, { onSuccess: () => router.push("/") });
        },
      },
    ];
    const recent = (runs ?? []).slice(0, 5).map<Command>((run) => ({
      id: `run-${run.id}`,
      label: run.title,
      hint: run.status,
      keywords: `run report ${run.title.toLowerCase()}`,
      icon: FileText,
      group: "Recent runs",
      run: go(`/app/runs/${run.id}`),
    }));
    return [...base, ...recent];
  }, [router, runs, logout]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (c) => c.label.toLowerCase().includes(needle) || c.keywords.includes(needle),
    );
  }, [commands, query]);

  // keep the selected option visible
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${selected}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const groups = useMemo(() => {
    const map = new Map<string, { command: Command; index: number }[]>();
    filtered.forEach((command, index) => {
      const list = map.get(command.group) ?? [];
      list.push({ command, index });
      map.set(command.group, list);
    });
    return map;
  }, [filtered]);

  return (
    <dialog
      ref={dialogRef}
      onClose={() => setOpen(false)}
      onClick={(e) => {
        if (e.target === dialogRef.current) setOpen(false);
      }}
      className={cn(
        "m-auto mt-[12dvh] w-[calc(100vw-2rem)] max-w-lg rounded-lg border border-border bg-surface-raised p-0 text-foreground shadow-2xl",
        "backdrop:bg-black/55 backdrop:backdrop-blur-[2px] open:animate-sheet-in",
      )}
      aria-label="Command palette"
    >
      {/* the header row IS the field — the input draws no chrome of its own,
          and focus reads off the row's bottom accent */}
      <div className="flex items-center gap-3 border-b border-border px-4 transition-colors focus-within:border-primary/40">
        <Search className="size-4 shrink-0 text-faint" aria-hidden />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setSelected((s) => Math.min(s + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setSelected((s) => Math.max(s - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              filtered[selected]?.run();
            }
          }}
          placeholder="Type a command or search…"
          aria-label="Search commands"
          role="combobox"
          aria-expanded="true"
          aria-controls="cmd-listbox"
          aria-autocomplete="list"
          aria-activedescendant={filtered.length > 0 ? `cmd-opt-${selected}` : undefined}
          data-no-focus-ring=""
          className="h-12 w-full bg-transparent text-[15px] placeholder:text-faint focus:outline-none"
        />
        <kbd className="hidden shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-faint sm:block">
          esc
        </kbd>
      </div>

      <ul ref={listRef} id="cmd-listbox" className="scroll-fade-bottom max-h-[40dvh] overflow-y-auto p-2 pb-4" role="listbox">
        {filtered.length === 0 && (
          <li className="px-3 py-6 text-center text-sm text-faint">
            Nothing matches “{query}”.
          </li>
        )}
        {[...groups.entries()].map(([group, items]) => (
          <li key={group}>
            <p className="tag-label px-3 pb-1 pt-2.5 text-faint">{group}</p>
            <ul>
              {items.map(({ command, index }) => (
                <li key={command.id}>
                  <button
                    type="button"
                    id={`cmd-opt-${index}`}
                    data-index={index}
                    role="option"
                    aria-selected={selected === index}
                    onMouseEnter={() => setSelected(index)}
                    onClick={() => command.run()}
                    className={cn(
                      "relative flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm",
                      selected === index
                        ? "bg-primary-soft text-primary"
                        : "text-foreground",
                    )}
                  >
                    {/* the tick — the archive's selection mark, not just a wash */}
                    {selected === index && (
                      <span
                        aria-hidden
                        className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary"
                      />
                    )}
                    <command.icon className="size-4 shrink-0 opacity-70" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{command.label}</span>
                    {command.hint && (
                      /* one metadata register: mono 11px, same as the kbd legend */
                      <span className="shrink-0 font-mono text-[11px] text-faint">{command.hint}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      {/* the quiet legend — keyboard grammar, machine register */}
      <p
        aria-hidden
        className="flex items-center gap-3 border-t border-border px-4 py-2 font-mono text-[10px] tracking-wide text-faint"
      >
        <span>↑↓ navigate</span>
        <span>↵ run</span>
        <span>esc close</span>
      </p>
    </dialog>
  );
}
