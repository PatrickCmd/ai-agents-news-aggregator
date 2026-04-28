import { ArrowRightIcon } from "lucide-react";

export function SampleDigestCard() {
  return (
    <div
      aria-hidden
      className="relative w-full max-w-md rotate-[-2deg] rounded-lg border border-[var(--rule)] bg-[var(--surface)] p-6 shadow-[0_30px_60px_-20px_rgba(0,0,0,0.5)]"
    >
      <p className="font-mono text-[0.65rem] uppercase tracking-[0.2em] text-[var(--ink-dim)]">
        Apr 27 → Apr 28
      </p>
      <h3 className="mt-3 font-display text-xl leading-snug text-balance">
        The week MCP went mainstream — and the testing problem nobody solved.
      </h3>
      <p className="mt-2 text-sm text-[var(--ink-dim)]">
        agent reliability · MCP tooling · production testing
      </p>
      <ul className="mt-5 space-y-3 border-t border-[var(--rule)] pt-4">
        {[
          { rank: 1, title: "Persistent multi-agent conversations with OpenAI Agents SDK", score: 97 },
          { rank: 2, title: "Building AI agents we can't test or debug", score: 95 },
          { rank: 3, title: "AI agents need route, boundary, and receipt — not autonomy", score: 93 },
        ].map((a) => (
          <li key={a.rank} className="flex items-start gap-3">
            <span className="font-display text-base text-[var(--ink-dim)]">{a.rank}</span>
            <span className="flex-1 text-sm leading-snug">{a.title}</span>
            <span className="inline-flex h-5 min-w-[2rem] items-center justify-center rounded-sm bg-primary px-1.5 font-mono text-[0.7rem] tabular-nums text-primary-foreground">
              {a.score}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-5 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.16em] text-primary">
        Read <ArrowRightIcon className="h-3 w-3" />
      </p>
    </div>
  );
}
