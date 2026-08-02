import type { Metadata, Viewport } from "next";
import { Fraunces, Schibsted_Grotesk, Spline_Sans_Mono } from "next/font/google";
import { siteConfig } from "@/config/site.config";
import { themeConfig, themeCss } from "@/config/theme.config";
import "./globals.css";

const themeBootScript = `
try {
  var stored = localStorage.getItem("clannon.theme");
  var theme = stored === "light" || stored === "dark" || stored === "system"
    ? stored
    : (location.pathname.indexOf("/app") === 0 ? "dark" : "light");
  var dark =
    theme === "dark" ||
    (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle("dark", dark);
} catch (_) {}
document.addEventListener("click", function (event) {
  var target = event.target;
  var button = target instanceof Element ? target.closest("[data-theme-toggle]") : null;
  if (button) {
    var root = document.documentElement;
    var current = root.dataset.theme || "light";
    var resolved = root.classList.contains("dark") ? "dark" : "light";
    var next = current === "system"
      ? (resolved === "dark" ? "light" : "dark")
      : (current === "light" ? "dark" : "system");
    try { localStorage.setItem("clannon.theme", next); } catch (_) {}
    var nextDark = next === "dark" ||
      (next === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.theme = next;
    root.classList.toggle("dark", nextDark);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (item) {
      item.setAttribute("aria-label", next + " theme — change theme");
    });
    return;
  }
  var menu = target instanceof Element ? target.closest("[data-mobile-menu]") : null;
  if (menu && target.closest("a")) menu.removeAttribute("open");
});
document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;
  document.querySelectorAll("[data-mobile-menu][open]").forEach(function (menu) {
    menu.removeAttribute("open");
  });
});
`;

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT", "WONK"],
  display: "swap",
});

const schibsted = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin"],
  display: "swap",
});

const splineMono = Spline_Sans_Mono({
  variable: "--font-spline-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.url),
  title: {
    default: `${siteConfig.name} — ${siteConfig.tagline}`,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
  applicationName: siteConfig.name,
  keywords: [
    "research automation",
    "AI research",
    "client research",
    "freelancer tools",
    "agency tools",
  ],
  openGraph: {
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
    type: "website",
    siteName: siteConfig.name,
  },
  robots: { index: true, follow: true },
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: siteConfig.name,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    // mirror the real background tokens so the browser chrome matches the page
    { media: "(prefers-color-scheme: light)", color: themeConfig.light.background },
    { media: "(prefers-color-scheme: dark)", color: themeConfig.dark.background },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-scroll-behavior="smooth"
      className={`${fraunces.variable} ${schibsted.variable} ${splineMono.variable} h-full antialiased`}
    >
      <head>
        {/* Tiny, trusted inline boot keeps theme flash-free without paying the
            request and beforeInteractive runtime cost on every public page. */}
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body className="grain min-h-full flex flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2.5 focus:text-sm focus:font-medium focus:text-primary-foreground"
        >
          Skip to content
        </a>
        {/* color tokens, generated from src/config/theme.config.ts */}
        <style>{themeCss()}</style>
        {children}
      </body>
    </html>
  );
}
