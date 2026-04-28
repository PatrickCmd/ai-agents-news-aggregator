"use client";

import { use } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useDigest } from "@/lib/hooks/useDigest";
import { RankedArticleCard } from "@/components/digest/RankedArticleCard";
import { DigestDetailSkeleton } from "@/components/digest/DigestDetailSkeleton";
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/types/api";

// Static export: pre-render no specific IDs. The route resolves to a single
// /digests/[id]/index.html shell that hydrates and fetches client-side.
// Without this, `next build` errors on dynamic routes for static export.
export async function generateStaticParams() {
  return [];
}

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${fmt(start)} — ${fmt(end)}`;
}

export default function DigestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const numericId = Number(id);
  const { data, isLoading, error } = useDigest(numericId);

  if (isLoading) return <DigestDetailSkeleton />;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Digest not found.</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <article className="prose dark:prose-invert max-w-3xl mx-auto">
      <header className="not-prose">
        <p className="text-sm text-muted-foreground">{formatPeriod(data.period_start, data.period_end)}</p>
        <h1 className="text-3xl font-bold mt-1">Your digest</h1>
        {data.top_themes.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {data.top_themes.map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </header>
      {data.intro && <p className="lead">{data.intro}</p>}
      <ol className="not-prose list-none p-0 space-y-6 mt-8">
        {data.ranked_articles.map((a, i) => (
          <RankedArticleCard key={a.article_id} article={a} rank={i + 1} />
        ))}
      </ol>
    </article>
  );
}
