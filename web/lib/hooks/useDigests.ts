"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { DigestListResponse } from "@/lib/types/api";

export const QK_DIGESTS = ["digests"] as const;

const PAGE_SIZE = 10;

export function useDigestsList() {
  const api = useApiClient();
  return useInfiniteQuery({
    queryKey: QK_DIGESTS,
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (pageParam !== null) qs.set("before", String(pageParam));
      return api.request<DigestListResponse>(`/v1/digests?${qs}`);
    },
    getNextPageParam: (last) => last.next_before,
  });
}
