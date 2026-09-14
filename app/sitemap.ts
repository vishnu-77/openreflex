import type { MetadataRoute } from "next";
import { GUIDES } from "@/lib/guides";
import { absoluteUrl, LAST_UPDATED } from "@/lib/seo";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date(LAST_UPDATED);
  return [
    { url: SITE_URL, lastModified, changeFrequency: "weekly", priority: 1 },
    { url: absoluteUrl("/docs"), lastModified, changeFrequency: "weekly", priority: 0.9 },
    ...GUIDES.map((guide) => ({
      url: absoluteUrl(`/${guide.slug}`),
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];
}
