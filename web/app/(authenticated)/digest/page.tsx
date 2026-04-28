"use client";

import { useSearchParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useDigest } from "@/lib/hooks/useDigest";
import { RankedArticleCard } from "@/components/digest/RankedArticleCard";
import { DigestDetailSkeleton } from "@/components/digest/DigestDetailSkeleton";
import { ApiError } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${fmt(start)} — ${fmt(end)}`;
}

export default function DigestDetailPage() {
  const params = useSearchParams();
  const idParam = params.get("id");
  const numericId = idParam ? Number(idParam) : NaN;
  const idValid = Number.isFinite(numericId);

  const { data, isLoading, error } = useDigest(idValid ? numericId : 0);

  if (!idValid) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-3xl">
        <AlertDescription>Missing or invalid digest id.</AlertDescription>
      </Alert>
    );
  }

  if (isLoading) return <DigestDetailSkeleton />;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-3xl">
        <AlertDescription>Digest not found.</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <article className="mx-auto max-w-3xl space-y-8 py-6">
      <header className="space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          {formatPeriod(data.period_start, data.period_end)}
        </p>
        <h1 className="text-balance font-display text-5xl leading-[1.05]">
          Your digest<span className="text-primary">.</span>
        </h1>
        {data.top_themes.length > 0 && (
          <p className="text-sm text-[var(--ink-dim)]">
            {data.top_themes.join(" · ")}
          </p>
        )}
      </header>

      {data.intro && (
        <p className="text-pretty text-lg leading-relaxed text-[var(--ink)]/90">
          {data.intro}
        </p>
      )}

      <ol className="list-none space-y-4 p-0">
        {data.ranked_articles.map((a, i) => (
          <li key={a.article_id}>
            <RankedArticleCard article={a} rank={i + 1} />
          </li>
        ))}
      </ol>
    </article>
  );
}
