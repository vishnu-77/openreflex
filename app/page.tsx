import { Footer } from "@/components/Footer";
import { GraphExplorer } from "@/components/GraphExplorer";
import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/HowItWorks";
import { Navbar } from "@/components/Navbar";
import { Privacy } from "@/components/Privacy";
import { PriorWork } from "@/components/PriorWork";
import { Quickstart } from "@/components/Quickstart";
import { ResearchIdea } from "@/components/ResearchIdea";
import { Shipped } from "@/components/Shipped";

export default function Home() {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink focus:px-3 focus:py-2 focus:text-bg"
      >
        Skip to content
      </a>
      <Navbar />
      <main id="main">
        <Hero />
        <div className="view-builder">
          <HowItWorks />
          <Quickstart />
          <Privacy />
          <Shipped />
        </div>
        <div className="view-research">
          <ResearchIdea />
          <GraphExplorer />
          <PriorWork />
        </div>
      </main>
      <Footer />
    </>
  );
}
