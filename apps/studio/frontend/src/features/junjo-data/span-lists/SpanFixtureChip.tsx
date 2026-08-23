export function SpanFixtureChip({ fixture }: { fixture: boolean }) {
  if (!fixture) return null

  return (
    <span
      data-span-modifier="fixture"
      className="inline-flex shrink-0 rounded-full border border-zinc-300 bg-zinc-100 px-1.5 py-0.5 text-[10px] font-light leading-none text-zinc-600 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
    >
      Fixture
    </span>
  )
}
