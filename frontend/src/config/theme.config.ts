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
     muted, ~7.5:1 for faint) instead of the usual pale-gray treatment.
     Pass 3: background sits a full step BELOW surface so cards physically
     lift instead of leaning on hairlines — same temperature, lower value. */
  background: "#eee9db",
  surface: "#fcfaf4",
  "surface-raised": "#ffffff",
  /* the artifact surface — the delivered report's own paper */
  sheet: "#ffffff",
  foreground: "#121b14",
  muted: "#e3dcc8",
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

  border: "#d1c8b2",
  "border-strong": "#a3987b",
  "edge-light": "rgba(255, 255, 255, 0.65)",
  /* the dendrochronology line — a structural ink line that stays legible on
     paper (border-strong washes out at ring stroke widths). ~4:1 on surface. */
  "ring-line": "#7a7052",
  ring: "#285539",

  destructive: "#a83a28",
  "destructive-hover": "#8f2f20",
  "destructive-foreground": "#f7f5ec",
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
  "stage-bg": "#e8e2ce",
  "stage-bloom": "rgba(40, 85, 57, 0.13)",
  "stage-ember": "rgba(124, 84, 16, 0.10)",
  "stage-vignette": "rgba(22, 33, 26, 0.12)",
  "glass-bg": "rgba(252, 250, 244, 0.66)",
  "glass-border": "rgba(22, 33, 26, 0.14)",
  glow: "rgba(40, 85, 57, 0.30)",
};

const dark: TokenSet = {
  /* green-cast ink, never slate. Pass 3: the elevation ladder is REAL now —
     canvas deepened (warmer-black, cast intact), raised lifted ~+5 L*, and a
     dedicated `sheet` for the delivered artifact (warm paper-cast, the "lit
     sheet on a dark desk"). Raised dark surfaces may carry shadows + a 1px
     `edge-light` top hairline (the instrument-panel cue). */
  background: "#0a0f0b",
  surface: "#131c15",
  "surface-raised": "#1d2a20",
  sheet: "#2c3424",
  foreground: "#e9ede0",
  muted: "#182219",
  "muted-foreground": "#a6b59d",
  "faint-foreground": "#8d9c85",

  primary: "#74c08a",
  "primary-hover": "#89cf9d",
  "primary-foreground": "#0b1410",
  "primary-soft": "#1b2d20",

  memory: "#ddab4f",
  "memory-soft": "#2c2313",

  border: "rgba(233, 237, 224, 0.11)",
  "border-strong": "rgba(233, 237, 224, 0.24)",
  "edge-light": "rgba(240, 244, 230, 0.09)",
  "ring-line": "rgba(233, 237, 224, 0.32)",
  ring: "#74c08a",

  destructive: "#e0735c",
  "destructive-hover": "#e88a72",
  "destructive-foreground": "#200d08",
  "destructive-soft": "#311b16",
  success: "#6fb583",
  warning: "#d9a84e",

  /* the log spectrum is the strongest anti-default signal — one notch of
     extra chroma so it survives 11px mono on ink */
  "log-route": "#74c08a",
  "log-expert": "#b5a1ee",
  "log-tool": "#61c6d9",
  "log-memory": "#ddab4f",
  "log-answer": "#e9ede0",

  /* the stage — dark: "the deep", a green-black field lit from within
     by a moss bloom and an amber ember, edges falling into shadow.
     Also the 4th elevation step: one BELOW background, behind hero
     moments, so raised objects have somewhere to float from. */
  "stage-bg": "#060a07",
  "stage-bloom": "rgba(116, 192, 138, 0.20)",
  "stage-ember": "rgba(221, 171, 79, 0.12)",
  "stage-vignette": "rgba(0, 0, 0, 0.55)",
  "glass-bg": "rgba(10, 15, 11, 0.72)",
  "glass-border": "rgba(233, 237, 224, 0.10)",
  glow: "rgba(116, 192, 138, 0.45)",
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
