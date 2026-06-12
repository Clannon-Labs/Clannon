/**
 * Visual theme — every color token for both themes, editable here
 * without touching CSS. The root layout turns this into CSS custom
 * properties at render time; `globals.css` only maps the variables
 * into Tailwind utilities and never hardcodes a color.
 *
 * Fonts are the one visual choice that can't live here: next/font
 * loads them at build time in `src/app/layout.tsx` (swap them there —
 * one import + three variable names).
 */

type TokenSet = Record<string, string>;

const light: TokenSet = {
  /* paper + ink — paper slightly cooler/brighter so ink pops.
     Secondary text runs DARK here on purpose: small warm-gray type on warm
     paper reads muddy, so light mode matches dark mode's clarity (~9:1 for
     muted, ~7.5:1 for faint) instead of the usual pale-gray treatment. */
  background: "#f3efe4",
  surface: "#fcfaf4",
  "surface-raised": "#ffffff",
  foreground: "#121b14",
  muted: "#e8e2d2",
  "muted-foreground": "#39432f",
  "faint-foreground": "#48533d",

  /* moss / fern — a touch deeper for contrast on paper */
  primary: "#285539",
  "primary-hover": "#1f432c",
  "primary-foreground": "#f7f5ec",
  "primary-soft": "#dde6d1",

  /* amber = memory, always — deep enough to stay crisp at tag-label sizes */
  memory: "#6e4a0e",
  "memory-soft": "#f1e6cd",

  border: "#d4ccb8",
  "border-strong": "#bbb097",
  ring: "#285539",

  destructive: "#a83a28",
  "destructive-soft": "#f6e3de",
  success: "#285539",
  warning: "#6e4a0e",

  "log-route": "#285539",
  "log-expert": "#564487",
  "log-tool": "#1b5763",
  "log-memory": "#6e4a0e",
  "log-answer": "#121b14",

  /* the stage — the hero/CTA atmosphere (light: a sunlit conservatory;
     see the dark set for the cinematic counterpart). Consumed by the
     .stage / .glass / .glow-word utilities in globals.css. */
  "stage-bg": "#ede8d7",
  "stage-bloom": "rgba(40, 85, 57, 0.13)",
  "stage-ember": "rgba(124, 84, 16, 0.10)",
  "stage-vignette": "rgba(22, 33, 26, 0.12)",
  "glass-bg": "rgba(252, 250, 244, 0.66)",
  "glass-border": "rgba(22, 33, 26, 0.14)",
  glow: "rgba(40, 85, 57, 0.30)",
};

const dark: TokenSet = {
  /* green-cast ink, never slate */
  background: "#0c120d",
  surface: "#121a13",
  "surface-raised": "#18221a",
  foreground: "#e9ede0",
  muted: "#1c271e",
  "muted-foreground": "#a3b29a",
  "faint-foreground": "#8b9a83",

  primary: "#6fb583",
  "primary-hover": "#84c597",
  "primary-foreground": "#0b1410",
  "primary-soft": "#1a2a1e",

  memory: "#d9a84e",
  "memory-soft": "#2a2214",

  border: "rgba(233, 237, 224, 0.1)",
  "border-strong": "rgba(233, 237, 224, 0.22)",
  ring: "#6fb583",

  destructive: "#e0735c",
  "destructive-soft": "#311b16",
  success: "#6fb583",
  warning: "#d9a84e",

  "log-route": "#6fb583",
  "log-expert": "#a795d9",
  "log-tool": "#6cb9c7",
  "log-memory": "#d9a84e",
  "log-answer": "#e9ede0",

  /* the stage — dark: "the deep", a green-black field lit from within
     by a moss bloom and an amber ember, edges falling into shadow */
  "stage-bg": "#070d08",
  "stage-bloom": "rgba(111, 181, 131, 0.20)",
  "stage-ember": "rgba(217, 168, 78, 0.12)",
  "stage-vignette": "rgba(0, 0, 0, 0.55)",
  "glass-bg": "rgba(12, 18, 13, 0.72)",
  "glass-border": "rgba(233, 237, 224, 0.10)",
  glow: "rgba(111, 181, 131, 0.45)",
};

export const themeConfig = { light, dark };

function block(selector: string, tokens: TokenSet, extra = ""): string {
  const vars = Object.entries(tokens)
    .map(([name, value]) => `--${name}: ${value};`)
    .join(" ");
  return `${selector} { ${vars} ${extra} }`;
}

/** The stylesheet injected by the root layout. */
export function themeCss(): string {
  return [
    block(":root", light),
    block(".dark", dark, "color-scheme: dark;"),
  ].join("\n");
}
