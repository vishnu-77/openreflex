import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CopyButton } from "@/components/CopyButton";
import { JsonLd } from "@/components/JsonLd";
import { PageShell } from "@/components/PageShell";
import { GUIDES, guideBySlug, type GuideStep } from "@/lib/guides";
import { articleJsonLd, breadcrumbJsonLd, pageMetadata } from "@/lib/seo";
import { LINKS } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return GUIDES.map((guide) => ({ agent: guide.slug }));
}

type Props = { params: Promise<{ agent: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const guide = guideBySlug((await params).agent);
  if (!guide) return {};
  return pageMetadata({ title: guide.title, description: guide.description, path: `/${guide.slug}` });
}

function Steps({ steps }: { steps: GuideStep[] }) {
  return (
    <ol className="mt-5 space-y-5">
      {steps.map((step, index) => (
        <li key={step.note} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
          <span className="pt-0.5 font-mono text-[0.85rem] tabular-nums text-accent">{index + 1}</span>
          <div className="min-w-0">
            <p className="text-text">{step.note}</p>
            {step.command && (
              <div className="mt-2 flex items-center gap-3 rounded-md bg-term py-1.5 pl-4 pr-1.5 font-mono text-[0.88rem] text-term-text">
                <span className="select-none text-term-dim">$</span>
                <code className="min-w-0 flex-1 break-all sm:break-normal">{step.command}</code>
                <CopyButton text={step.command} />
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export default async function GuidePage({ params }: Props) {
  const guide = guideBySlug((await params).agent);
  if (!guide) notFound();
  const path = `/${guide.slug}`;
  const crumbs = [
    { name: "Home", path: "/" },
    { name: "Docs", path: "/docs" },
    { name: guide.agent, path },
  ];
  const others = GUIDES.filter((item) => item.slug !== guide.slug);

  return (
    <PageShell crumbs={crumbs}>
      <JsonLd data={[articleJsonLd({ title: guide.title, description: guide.description, path }), breadcrumbJsonLd(crumbs)]} />
      <article>
        <header className="mt-8 border-b border-line pb-10">
          <p className="font-mono text-[0.8rem] text-accent">Integration guide</p>
          <h1 className="mt-4 font-serif text-[2.6rem] leading-[1.05] tracking-[-0.02em] text-ink sm:text-[3.4rem]">{guide.h1}</h1>
          <p className="mt-6 max-w-[46rem] text-[1.08rem] leading-[1.75] text-muted">{guide.lead}</p>
        </header>

        <section aria-labelledby="benefits" className="mt-12">
          <h2 id="benefits" className="text-[1.6rem] font-semibold tracking-tight text-ink">
            What OpenReflex adds to {guide.agent}
          </h2>
          <div className="mt-6 grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-3">
            {guide.benefits.map((benefit) => (
              <div key={benefit.title} className="bg-panel p-6">
                <h3 className="font-semibold text-ink">{benefit.title}</h3>
                <p className="mt-2 leading-relaxed text-muted">{benefit.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="install" className="mt-14">
          <h2 id="install" className="text-[1.6rem] font-semibold tracking-tight text-ink">
            Install OpenReflex for {guide.agent}
          </h2>
          <Steps steps={guide.install} />
          {guide.alternative && (
            <div className="mt-10 rounded-lg border border-line bg-panel p-6">
              <h3 className="font-semibold text-ink">{guide.alternative.heading}</h3>
              <Steps steps={guide.alternative.steps} />
            </div>
          )}
          <p className="mt-6 text-muted">
            Check the setup any time with <code className="font-mono text-[0.9em] text-ink">openreflex doctor</code>. Nothing is
            recorded until a project is enabled.
          </p>
        </section>

        <section aria-labelledby="how" className="mt-14">
          <h2 id="how" className="text-[1.6rem] font-semibold tracking-tight text-ink">
            How it works in {guide.agent}
          </h2>
          <div className="mt-6 overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[520px] border-collapse text-left">
              <thead className="bg-panel">
                <tr className="text-[0.88rem] text-muted">
                  <th scope="col" className="w-[36%] px-5 py-3 font-medium">Hook event</th>
                  <th scope="col" className="px-5 py-3 font-medium">What OpenReflex does</th>
                </tr>
              </thead>
              <tbody>
                {guide.events.map((row) => (
                  <tr key={row.event} className="border-t border-line align-top">
                    <td className="px-5 py-3 font-mono text-[0.88rem] text-ink">{row.event}</td>
                    <td className="px-5 py-3 leading-relaxed text-text">{row.what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="mt-6 space-y-3">
            {guide.notes.map((note) => (
              <li key={note} className="flex gap-3 leading-relaxed text-text">
                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                {note}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="questions" className="mt-14">
          <h2 id="questions" className="text-[1.6rem] font-semibold tracking-tight text-ink">
            Common questions
          </h2>
          <dl className="mt-4">
            {guide.faq.map((item) => (
              <div key={item.q} className="border-t border-line py-5">
                <dt className="font-semibold text-ink">{item.q}</dt>
                <dd className="mt-2 leading-relaxed text-muted">{item.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="more" className="mt-14 rounded-lg border border-line bg-panel p-6 sm:p-8">
          <h2 id="more" className="text-[1.25rem] font-semibold text-ink">
            Other integrations
          </h2>
          <ul className="mt-4 flex flex-wrap gap-3">
            {others.map((item) => (
              <li key={item.slug}>
                <a href={`/${item.slug}`} className="inline-flex h-10 items-center rounded-md border border-line-strong px-4 text-ink hover:bg-bg">
                  OpenReflex for {item.agent}
                </a>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-muted">
            Full CLI and MCP reference in the <a href="/docs" className="text-accent underline underline-offset-4">docs</a>, and the
            source on <a href={LINKS.github} className="text-accent underline underline-offset-4">GitHub</a>.
          </p>
        </section>
      </article>
    </PageShell>
  );
}
