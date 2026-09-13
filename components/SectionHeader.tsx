export function SectionHeader({ id, title, intro }: { id: string; title: string; intro: string }) {
  return (
    <div className="mb-10 border-b border-line pb-8">
      <h2 id={`${id}-title`} className="font-serif text-[2.1rem] leading-[1.08] tracking-[-0.015em] text-ink sm:text-[2.6rem]">
        {title}
      </h2>
      <p className="mt-4 max-w-[42rem] text-[1.05rem] leading-[1.7] text-muted">{intro}</p>
    </div>
  );
}
