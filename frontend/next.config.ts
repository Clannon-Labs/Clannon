import type { NextConfig } from "next";
import os from "node:os";
import type { NetworkInterfaceInfo } from "node:os";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const isDev = process.env.NODE_ENV === "development";

// Every non-internal IPv4 address of this machine. Used for allowedDevOrigins
// so opening the dev app over the LAN (e.g. a phone) doesn't trip Next's
// cross-origin dev-resource guard — auto-detected, so a new IP never breaks it.
const lanHosts = Object.values(os.networkInterfaces())
  .flat()
  .filter((iface): iface is NetworkInterfaceInfo => !!iface && iface.family === "IPv4" && !iface.internal)
  .map((iface) => iface.address);

/**
 * Security headers. The CSP allows 'unsafe-inline' for script/style
 * because Next.js App Router injects inline bootstrapping — move to
 * nonce-based CSP via middleware when auth cookies go live.
 * 'unsafe-eval' is DEV ONLY: React dev tooling (callstack
 * reconstruction, fast refresh) needs eval(); production never gets it.
 * connect-src is widened to the configured backend origin only.
 */
const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self'",
      `connect-src 'self' ${apiBaseUrl}`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
      // Production-only: forces http→https. In dev this breaks LAN access
      // (http://<lan-ip>:3000) because the browser upgrades every _next/static
      // asset to https, which isn't served — localhost is exempt, so it only
      // bites over the network. Production serves HTTPS, so it stays on there.
      ...(isDev ? [] : ["upgrade-insecure-requests"]),
    ].join("; "),
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
  // Dev-only: lets HMR/fast-refresh work when the app is opened over the LAN
  // (e.g. from a phone). Auto-detected from this machine's interfaces, so a
  // new IP needs no edit. Ignored in production.
  allowedDevOrigins: lanHosts,
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
