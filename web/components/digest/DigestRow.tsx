import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";
import type { DigestSummaryOut } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(start)} → ${fmt(end)}`;
}

function firstSentence(text: string | null): string {
  if (!text) return "Your digest";
  const m = text.match(/^[^.!?]+[.!?]/);
  return (m ? m[0] : text).trim();
}

export function DigestRow({ digest }: { digest: DigestSummaryOut }) {
  return (
    <li className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] py-6 first:border-t-0 sm:gap-6">
      <div className="col-span-12 sm:col-span-3">
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          {formatPeriod(digest.period_start, digest.period_end)}
        </p>
        <p className="mt-2 font-mono text-xs text-[var(--ink-dim)]">
          {digest.article_count} articles
        </p>
      </div>
      <div className="col-span-12 space-y-2 sm:col-span-9">
        <h2 className="text-balance font-display text-2xl leading-snug">
          <Link
            href={`/digest?id=${digest.id}`}
            className="text-[var(--ink)] underline-offset-4 hover:underline"
          >
            {firstSentence(digest.intro)}
          </Link>
        </h2>
        {digest.top_themes.length > 0 && (
          <p className="text-sm text-[var(--ink-dim)]">
            {digest.top_themes.slice(0, 5).join(" · ")}
          </p>
        )}
        <Link
          href={`/digest?id=${digest.id}`}
          className="inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.16em] text-primary hover:underline"
        >
          Read <ArrowRightIcon className="h-3 w-3" />
        </Link>
      </div>
    </li>
  );
}
