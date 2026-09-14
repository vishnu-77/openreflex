import type { Metadata } from "next";
import { LINKS, SITE_URL } from "./site";

export const VERSION = "0.1.2";
export const LAST_UPDATED = "2026-09-14";

export function absoluteUrl(path = "/") {
  return new URL(path, SITE_URL).toString();
}

/** Page metadata with a canonical URL and matching Open Graph / Twitter fields. */
export function pageMetadata({ title, description, path }: { title: string; description: string; path: string }): Metadata {
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", url: absoluteUrl(path), siteName: "OpenReflex", title, description },
    twitter: { card: "summary_large_image", title, description },
  };
}

const author = { "@type": "Person", name: "vishnu-77", url: "https://github.com/vishnu-77" };

export function softwareJsonLd(description: string) {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "OpenReflex",
    url: SITE_URL,
    description,
    applicationCategory: "DeveloperApplication",
    applicationSubCategory: "AI coding agent plugin",
    operatingSystem: "Windows, macOS, Linux",
    softwareVersion: VERSION,
    softwareRequirements: "Python 3.11 or newer",
    license: "https://opensource.org/licenses/MIT",
    isAccessibleForFree: true,
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    downloadUrl: LINKS.pypi,
    installUrl: LINKS.pypi,
    codeRepository: LINKS.github,
    sameAs: [LINKS.github, LINKS.pypi],
    author,
    keywords: "Claude Code, Codex, Cursor, OpenCode, MCP, AI coding agents, agent memory, loop detection, local-first",
  };
}

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "OpenReflex",
    url: SITE_URL,
    inLanguage: "en",
    publisher: author,
  };
}

export function articleJsonLd({ title, description, path }: { title: string; description: string; path: string }) {
  return {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: title,
    description,
    url: absoluteUrl(path),
    inLanguage: "en",
    dateModified: LAST_UPDATED,
    author,
    publisher: author,
    about: { "@type": "SoftwareApplication", name: "OpenReflex", url: SITE_URL },
  };
}

export function breadcrumbJsonLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}
