import type { MetadataRoute } from "next";
import { DESCRIPTION } from "@/lib/site";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OpenReflex",
    short_name: "OpenReflex",
    description: DESCRIPTION,
    start_url: "/",
    display: "standalone",
    background_color: "#F6F2E8",
    theme_color: "#F6F2E8",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
