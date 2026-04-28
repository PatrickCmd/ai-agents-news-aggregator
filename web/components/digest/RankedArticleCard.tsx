import { Badge } from "@/components/ui/badge";
import type { RankedArticle } from "@/lib/types/api";

export function RankedArticleCard({ article, rank }: { article: RankedArticle; rank: number }) {
  return (
    <li className="flex gap-4 border-b last:border-b-0 pb-6">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-muted flex items-center justify-center font-bold">
        {rank}
      </div>
      <div className="flex-1 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold hover:underline"
          >
            {article.title}
          </a>
          <Badge variant="outline" className="flex-shrink-0">
            {article.score}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{article.summary}</p>
        <p className="text-xs text-muted-foreground italic border-l-2 pl-3">
          <strong className="not-italic">Why this article: </strong>
          {article.why_ranked}
        </p>
      </div>
    </li>
  );
}
