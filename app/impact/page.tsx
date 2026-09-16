import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { ImpactLandscape } from "@/components/ImpactGlobe";
import { Navbar } from "@/components/Navbar";
import { getImpactSnapshot } from "@/lib/impact";

export const metadata: Metadata = {
  title: "Impact | OpenReflex",
  description: "A living visualisation of aggregate inference avoided by OpenReflex, with transparent environmental-equivalence methodology.",
  alternates: { canonical: "/impact" },
};

export default function ImpactPage() {
  const impact = getImpactSnapshot();

  return (
    <>
      <a
        href="#impact-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink focus:px-3 focus:py-2 focus:text-bg"
      >
        Skip to impact
      </a>
      <Navbar showViewToggle={false} />
      <main id="impact-main">
        <section className="border-b border-line">
          <div className="mx-auto max-w-[1320px] px-5 pb-4 pt-16 sm:px-10 sm:pt-24">
            <p className="font-mono text-[0.76rem] uppercase tracking-[0.14em] text-accent">OpenReflex / Impact</p>
            <div className="mt-5 grid gap-7 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,0.7fr)] lg:items-end lg:gap-20">
              <h1 className="max-w-[760px] font-serif text-[3rem] leading-[0.98] tracking-[-0.025em] text-ink sm:text-[4.7rem]">
                Less inference. A living record of what was avoided.
              </h1>
              <p className="max-w-[34rem] text-[1.02rem] leading-7 text-muted lg:pb-2">
                OpenReflex turns aggregate token efficiency into a growing landscape. The forest is deliberately illustrative; the numbers remain separate, sourced and auditable. As avoided inference grows, the weather and ecosystem become richer without claiming that virtual trees are physical carbon offsets.
              </p>
            </div>
          </div>

          <ImpactLandscape impact={impact} />
        </section>
      </main>
      <Footer />
    </>
  );
}
