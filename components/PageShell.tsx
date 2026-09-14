import { ChevronRight } from "lucide-react";
import { Footer } from "./Footer";
import { Navbar } from "./Navbar";

export function PageShell({
  crumbs,
  children,
}: {
  crumbs: { name: string; path: string }[];
  children: React.ReactNode;
}) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink focus:px-3 focus:py-2 focus:text-bg"
      >
        Skip to content
      </a>
      <Navbar showViewToggle={false} />
      <main id="main" className="border-b border-line">
        <div className="mx-auto max-w-[1080px] px-5 pb-20 pt-10 sm:px-10 sm:pb-28">
          <nav aria-label="Breadcrumb">
            <ol className="flex flex-wrap items-center gap-1.5 text-[0.88rem] text-muted">
              {crumbs.map((crumb, index) => (
                <li key={crumb.path} className="flex items-center gap-1.5">
                  {index > 0 && <ChevronRight size={14} aria-hidden="true" />}
                  {index === crumbs.length - 1 ? (
                    <span aria-current="page" className="text-ink">
                      {crumb.name}
                    </span>
                  ) : (
                    <a href={crumb.path} className="hover:text-ink">
                      {crumb.name}
                    </a>
                  )}
                </li>
              ))}
            </ol>
          </nav>
          {children}
        </div>
      </main>
      <Footer />
    </>
  );
}
