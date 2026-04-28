"use client";

import { Button } from "@/components/ui/button";
import { SparklesIcon } from "lucide-react";
import { useDigestsList } from "@/lib/hooks/useDigests";
import { useRemix } from "@/lib/hooks/useRemix";
import { DigestCard } from "@/components/digest/DigestCard";
import { DigestListSkeleton } from "@/components/digest/DigestListSkeleton";
import { EmptyState } from "@/components/digest/EmptyState";

export default function HomePage() {
  const list = useDigestsList();
  const remix = useRemix();

  const digests = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-3xl font-bold">Your digests</h1>
        <Button onClick={() => remix.mutate(24)} disabled={remix.isPending}>
          <SparklesIcon className="mr-2 h-4 w-4" />
          {remix.isPending ? "Triggering…" : "Remix now"}
        </Button>
      </header>

      {list.isLoading ? (
        <DigestListSkeleton />
      ) : digests.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {digests.map((d) => (
            <DigestCard key={d.id} digest={d} />
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" onClick={() => list.fetchNextPage()}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
