import Link from "next/link";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRightIcon } from "lucide-react";
import type { DigestSummaryOut } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(start)} → ${fmt(end)}`;
}

export function DigestCard({ digest }: { digest: DigestSummaryOut }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="text-sm text-muted-foreground">
          {formatPeriod(digest.period_start, digest.period_end)}
        </div>
        {digest.intro && (
          <p className="line-clamp-2 text-sm font-medium">{digest.intro}</p>
        )}
      </CardHeader>
      <CardContent className="flex-1">
        <div className="flex flex-wrap gap-1">
          {digest.top_themes.slice(0, 3).map((t) => (
            <Badge key={t} variant="secondary">
              {t}
            </Badge>
          ))}
        </div>
      </CardContent>
      <CardFooter className="flex items-center justify-between pt-2">
        <span className="text-sm text-muted-foreground">{digest.article_count} articles</span>
        <Link
          href={`/digests/${digest.id}`}
          className="text-sm font-medium text-primary hover:underline inline-flex items-center gap-1"
        >
          Read <ArrowRightIcon className="h-3 w-3" />
        </Link>
      </CardFooter>
    </Card>
  );
}
