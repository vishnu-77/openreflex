import { ImageResponse } from "next/og";

export const dynamic = "force-static";
export const alt = "OpenReflex: muscle memory for AI coding agents";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
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
          color: "#f5efe4",
          fontFamily: "Georgia, serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <svg width="64" height="64" viewBox="0 0 80 80">
            <path d="M40 15 A25 25 0 1 1 16.51 31.45" fill="none" stroke="#7cc9c8" strokeWidth="7" strokeLinecap="round" />
            <path
              d="M8.88 36.22 L16.51 31.45 L19.29 40.01"
              fill="none"
              stroke="#7cc9c8"
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="40" cy="40" r="8.5" fill="#7cc9c8" />
          </svg>
          <div style={{ fontSize: 40, fontFamily: "sans-serif", fontWeight: 600 }}>OpenReflex</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ fontSize: 88, lineHeight: 1, letterSpacing: -2 }}>Muscle memory for AI coding agents.</div>
          <div style={{ fontSize: 30, color: "#b7ad9f", fontFamily: "sans-serif" }}>
            Claude Code · Codex · Cursor · OpenCode. Local-first and open source.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 26,
            fontFamily: "monospace",
            color: "#9edce0",
            borderLeft: "4px solid #7cc9c8",
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
