import { ImageResponse } from "next/og";

export const dynamic = "force-static";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

const MARK =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="8 8 260 270" fill="none">' +
  '<path d="M32 23H145A78 78 0 0 1 157 181" stroke="#286A70" stroke-width="30" stroke-linecap="round"/>' +
  '<path d="M154 187L253 263" stroke="#286A70" stroke-width="28" stroke-linecap="round"/>' +
  '<path d="M100 107H85A62 62 0 0 0 23 169V258" stroke="#286A70" stroke-width="26" stroke-linecap="round"/>' +
  '<circle cx="127" cy="105" r="27" fill="#286A70"/>' +
  '<path d="M112 176H71V214" stroke="#286A70" stroke-width="19" stroke-linecap="round" stroke-linejoin="round"/>' +
  '<path d="M78 183L151 257" stroke="#286A70" stroke-width="21" stroke-linecap="round"/>' +
  "</svg>";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#F6F2E8" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(MARK)}`} width={116} height={120} alt="" />
      </div>
    ),
    size,
  );
}
