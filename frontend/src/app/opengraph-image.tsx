import { ImageResponse } from "next/og";
import { siteConfig } from "@/config/site.config";
import { BUILTIN_MARK_RINGS, BUILTIN_MARK_CORE_R } from "@/config/brand.config";

export const alt = `${siteConfig.name} — ${siteConfig.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Social share card: the ring mark on green ink, brand + tagline. */
export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          backgroundColor: "#0c120d",
          color: "#e9ede0",
          fontFamily: "Georgia, serif",
        }}
      >
        <svg width="120" height="120" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r={BUILTIN_MARK_CORE_R} fill="#6fb583" />
          {BUILTIN_MARK_RINGS.map((ring) => (
            <circle
              key={ring.r}
              cx="16"
              cy="16"
              r={ring.r}
              stroke="#6fb583"
              strokeWidth={ring.width}
              strokeLinecap="round"
              strokeDasharray={ring.dash}
              transform={`rotate(${ring.rotate} 16 16)`}
            />
          ))}
        </svg>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 88, fontWeight: 500, letterSpacing: "-0.02em" }}>
            {siteConfig.name}
          </div>
          <div style={{ display: "flex", fontSize: 40, color: "#a3b29a", marginTop: 12 }}>
            Research that <span style={{ color: "#6fb583", marginLeft: 10 }}>remembers.</span>
          </div>
        </div>
        <div style={{ fontSize: 24, color: "#76856f", display: "flex" }}>
          brief in → parallel experts → quality filter → sourced report
        </div>
      </div>
    ),
    size,
  );
}
