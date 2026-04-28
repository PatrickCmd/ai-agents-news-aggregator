export function EmptyState() {
  return (
    <div className="space-y-3 border-t border-[var(--rule)] py-12 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
        empty
      </p>
      <h3 className="font-display text-2xl">No digests yet.</h3>
      <p className="mx-auto max-w-md text-sm text-[var(--ink-dim)]">
        Daily digests are generated at 00:00 EAT. Click <strong className="text-[var(--ink)]">Remix now</strong> above for an on-demand run — about 30–60 seconds.
      </p>
    </div>
  );
}
