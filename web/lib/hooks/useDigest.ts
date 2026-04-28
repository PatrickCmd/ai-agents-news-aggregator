"use client";

import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { DigestOut } from "@/lib/types/api";

export const qkDigest = (id: number) => ["digest", id] as const;

export function useDigest(id: number) {
  const api = useApiClient();
  return useQuery({
    queryKey: qkDigest(id),
    queryFn: () => api.request<DigestOut>(`/v1/digests/${id}`),
  });
}
