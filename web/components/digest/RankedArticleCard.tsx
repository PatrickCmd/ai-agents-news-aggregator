import { Card, CardContent } from "@/components/ui/card";
import { YouTubePreview } from "@/components/digest/YouTubePreview";
import { youtubeIdFromUrl } from "@/lib/utils/youtube";
import type { RankedArticle } from "@/lib/types/api";

export function RankedArticleCard({ article, rank }: { article: RankedArticle; rank: number }) {
  const ytId = youtubeIdFromUrl(article.url);

  return (
    <Card className="overflow-hidden">
      <CardContent className="grid grid-cols-12 gap-4 px-4 py-5 sm:gap-6 sm:px-6 sm:py-6">
        {/* Left gutter — rank + score chip */}
        <div className="col-span-2 flex flex-col items-start gap-2 sm:col-span-1">
          <span className="font-display text-3xl leading-none text-[var(--ink-dim)]">
            {rank}
          </span>
          <span
            className="inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded-sm bg-primary px-1.5 font-mono text-[0.78rem] tabular-nums leading-none tracking-tight text-primary-foreground"
            aria-label={`Score: ${article.score} out of 100`}
          >
            {article.score}
          </span>
        </div>

        {/* Body */}
        <div className="col-span-10 space-y-3 sm:col-span-11">
          {ytId && <YouTubePreview videoId={ytId} title={article.title} />}
          <h3 className="text-balance">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-display text-xl font-semibold leading-snug text-[var(--ink)] underline-offset-4 hover:underline"
            >
              {article.title}
            </a>
          </h3>
          <p className="text-pretty text-[0.95rem] leading-relaxed text-[var(--ink)]/90">
            {article.summary}
          </p>
          <blockquote className="border-l-2 border-primary pl-4 text-sm italic leading-relaxed text-[var(--ink-dim)]">
            <span className="not-italic font-mono text-[0.7rem] uppercase tracking-[0.18em] text-[var(--ink-dim)]/80">
              Why this article
            </span>
            <p className="mt-1">{article.why_ranked}</p>
          </blockquote>
        </div>
      </CardContent>
    </Card>
  );
}
