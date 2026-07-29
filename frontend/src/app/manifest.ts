import type { MetadataRoute } from "next";
import { siteConfig } from "@/config/site.config";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: siteConfig.name,
    short_name: siteConfig.name,
    description: siteConfig.description,
    start_url: "/app",
    display: "standalone",
    background_color: "#0c120d",
    theme_color: "#0c120d",
    icons: [{ src: "/icon.png", sizes: "305x305", type: "image/png" }],
  };
}
