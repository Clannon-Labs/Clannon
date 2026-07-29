import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { siteConfig } from "@/config/site.config";

export const alt = `${siteConfig.name} — ${siteConfig.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Social share card: reversed lockup, promise, and compact pipeline. */
export default async function OpenGraphImage() {
  const logoData = await readFile(
    join(process.cwd(), "public/brand/clannon-logo-reversed-dark.png"),
    "base64",
  );
  const logoSrc = `data:image/png;base64,${logoData}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          backgroundColor: "#0c120d",
          color: "#e9ede0",
          fontFamily: "Georgia, serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 56 }}>
          <img
            src={logoSrc}
            alt=""
            width={246}
            height={231}
            style={{ objectFit: "contain" }}
          />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              fontSize: 68,
              fontWeight: 500,
              lineHeight: 1.02,
              letterSpacing: "-0.025em",
            }}
          >
            <span>Research that</span>
            <span style={{ color: "#6fb583" }}>remembers.</span>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            borderTop: "1px solid #253429",
            paddingTop: 26,
            fontSize: 23,
            color: "#93a48c",
          }}
        >
          <span>brief in</span>
          <span>parallel experts</span>
          <span>quality filter</span>
          <span>sourced report</span>
        </div>
      </div>
    ),
    size,
  );
}
