"use client";

import { Button } from "@/components/ui/button";
import { SparklesIcon } from "lucide-react";
import { useDigestsList } from "@/lib/hooks/useDigests";
import { useRemix } from "@/lib/hooks/useRemix";
import { DigestRow } from "@/components/digest/DigestRow";
import { DigestListSkeleton } from "@/components/digest/DigestListSkeleton";
import { EmptyState } from "@/components/digest/EmptyState";

function todayLabel(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function DigestListSection() {
  const list = useDigestsList();
  const remix = useRemix();

  const digests = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="mx-auto max-w-3xl space-y-8 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--rule)] pb-6">
        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
            dispatch · {todayLabel()}
          </p>
          <h1 className="font-display text-4xl">
            Your digests<span className="text-primary">.</span>
          </h1>
        </div>
        <Button
          variant="outline"
          onClick={() => remix.mutate(24)}
          disabled={remix.isPending}
          className="font-mono text-xs uppercase tracking-[0.14em]"
        >
          <SparklesIcon className="mr-2 h-3.5 w-3.5" />
          {remix.isPending ? "Triggering…" : "Remix now"}
        </Button>
      </header>

      {list.isLoading ? (
        <DigestListSkeleton />
      ) : digests.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="list-none p-0">
          {digests.map((d) => (
            <DigestRow key={d.id} digest={d} />
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            onClick={() => list.fetchNextPage()}
            className="font-mono text-xs uppercase tracking-[0.14em]"
          >
            Load more
          </Button>
        </div>
      )}
    </section>
  );
}
