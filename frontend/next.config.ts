import type { NextConfig } from "next";
import os from "node:os";
import type { NetworkInterfaceInfo } from "node:os";
import { requireHttpBaseUrl } from "./src/config/url-policy";

const apiBaseUrl = requireHttpBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  "NEXT_PUBLIC_API_BASE_URL",
);
const devBackendUrl = process.env.CLANNON_DEV_BACKEND_URL;
const isDev = process.env.NODE_ENV === "development";

// Every non-internal IPv4 address of this machine. Used for allowedDevOrigins
// so opening the dev app over the LAN (e.g. a phone) doesn't trip Next's
// cross-origin dev-resource guard — auto-detected, so a new IP never breaks it.
function detectLanHosts(): string[] {
  if (!isDev) return [];

  try {
    return Object.values(os.networkInterfaces())
      .flat()
      .filter((iface): iface is NetworkInterfaceInfo => !!iface && iface.family === "IPv4" && !iface.internal)
      .map((iface) => iface.address);
  } catch {
    // LAN access is a dev convenience. Restricted containers can deny network
    // enumeration; localhost must keep working instead of breaking all builds.
    return [];
  }
}

const lanHosts = detectLanHosts();

/**
 * Build one CSP from validated configuration. Script/style 'unsafe-inline'
 * remains because the static
 * root layout contains the pre-hydration theme script and generated theme CSS,
 * while Next's nonce path requires per-request Proxy headers plus dynamic
 * rendering. Removing it is a separate rendering/performance migration, not a
 * header-only edit.
 * 'unsafe-eval' is DEV ONLY: React dev tooling (callstack
 * reconstruction, fast refresh) needs eval(); production never gets it.
 * connect-src is widened to the configured backend origin only.
 */
export function buildContentSecurityPolicy(backendUrl: string, development: boolean): string {
  const normalizedBackendUrl = requireHttpBaseUrl(backendUrl, "NEXT_PUBLIC_API_BASE_URL");
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    // Parsed serialization guarantees one CSP source expression, never raw env text.
    `connect-src 'self' ${new URL(normalizedBackendUrl).origin}`,
    // No product surface embeds frames; PDF blobs open in a separate browser tab.
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    // Production-only: forces http→https. In dev this breaks LAN access
    // (http://<lan-ip>:3000) because the browser upgrades every _next/static
    // asset to https, which isn't served — localhost is exempt, so it only
    // bites over the network. Production serves HTTPS, so it stays on there.
    ...(development ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: buildContentSecurityPolicy(apiBaseUrl, isDev),
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // wraps route navigations in document.startViewTransition() so the browser
  // can crossfade/morph between pages — powers the shared-element run-row →
  // run-page morph (matching view-transition-name per run id). Native API;
  // gated to prefers-reduced-motion in globals.css.
  experimental: {
    viewTransition: true,
  },
  // Dev-only: lets HMR/fast-refresh work when the app is opened over the LAN
  // (e.g. from a phone). Auto-detected from this machine's interfaces, so a
  // new IP needs no edit. Ignored in production.
  allowedDevOrigins: lanHosts,
  async rewrites() {
    // Root ./dev.sh gives local development one browser-visible origin:
    // Next owns :3000 and forwards /api/* to FastAPI's private :8000 listener.
    // Production keeps using NEXT_PUBLIC_API_BASE_URL directly; this rewrite
    // exists only when the launcher supplies its server-only target.
    if (!isDev || !devBackendUrl) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${devBackendUrl}/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
