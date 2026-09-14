import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { GraphExplorer } from "@/components/GraphExplorer";
import { Hero } from "@/components/Hero";
import { JsonLd } from "@/components/JsonLd";
import { HowItWorks } from "@/components/HowItWorks";
import { Navbar } from "@/components/Navbar";
import { Privacy } from "@/components/Privacy";
import { PriorWork } from "@/components/PriorWork";
import { Quickstart } from "@/components/Quickstart";
import { ReflexRecap } from "@/components/ReflexRecap";
import { ResearchEvidence } from "@/components/ResearchEvidence";
import { ResearchIdea } from "@/components/ResearchIdea";
import { ResearchRoadmap } from "@/components/ResearchRoadmap";
import { Shipped } from "@/components/Shipped";
import { softwareJsonLd, websiteJsonLd } from "@/lib/seo";
import { DESCRIPTION } from "@/lib/site";

// The Researcher view (?view=research) is the same document, so it shares this canonical URL.
export const metadata: Metadata = { alternates: { canonical: "/" } };

export default function Home() {
  return (
    <>
      <JsonLd data={[softwareJsonLd(DESCRIPTION), websiteJsonLd()]} />
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
          <ReflexRecap />
          <ResearchRoadmap />
          <GraphExplorer />
          <ResearchEvidence />
          <PriorWork />
        </div>
      </main>
      <Footer />
    </>
  );
}
