import { ImageResponse } from "next/og";
import { OG_LOGO, OG_LOGO_SVG } from "@/lib/logo-og";

export const dynamic = "force-static";
export const alt = "OpenReflex: muscle memory for AI coding agents";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const logoSrc =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${OG_LOGO.viewBox}">${OG_LOGO_SVG}</svg>`);

export default function OpengraphImage() {
  const logoHeight = 76;
  const logoWidth = Math.round((OG_LOGO.width / OG_LOGO.height) * logoHeight);
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "#101317",
          color: "#F5EFE4",
          fontFamily: "Georgia, serif",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoSrc} width={logoWidth} height={logoHeight} alt="" />
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ fontSize: 88, lineHeight: 1, letterSpacing: -2 }}>Muscle memory for AI coding agents.</div>
          <div style={{ fontSize: 30, color: "#A79F92", fontFamily: "sans-serif" }}>
            Claude Code, Codex, Cursor and OpenCode. Local-first and open source.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 26,
            fontFamily: "monospace",
            color: "#7CC9C8",
            borderLeft: "4px solid #7CC9C8",
            paddingLeft: 20,
          }}
        >
          $ pipx install openreflex
        </div>
      </div>
    ),
    size,
  );
}
