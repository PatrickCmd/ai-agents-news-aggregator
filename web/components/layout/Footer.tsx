export function Footer() {
  return (
    <footer className="mt-auto border-t border-[var(--rule)]">
      <div className="container flex flex-col items-center justify-between gap-2 py-4 text-xs sm:flex-row">
        <p className="font-mono uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          daily · ai-curated · ranked 0–100 · ~5 min read
        </p>
        <p className="font-mono text-[var(--ink-dim)]">v0.7.0</p>
      </div>
    </footer>
  );
}
