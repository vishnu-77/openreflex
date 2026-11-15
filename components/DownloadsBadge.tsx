/** Total PyPI downloads from pepy.tech, linked to the project's pepy page. */
export function DownloadsBadge({ className = "" }: { className?: string }) {
  return (
    <a
      href="https://pepy.tech/projects/openreflex"
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex ${className}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- a remote SVG badge in a static export */}
      <img
        src="https://static.pepy.tech/personalized-badge/openreflex?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLUE&right_color=ORANGE&left_text=downloads"
        alt="PyPI downloads of openreflex"
        height={20}
        loading="lazy"
      />
    </a>
  );
}
