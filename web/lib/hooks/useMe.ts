"use client";

import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { UserOut } from "@/lib/types/api";

export const QK_ME = ["me"] as const;

export function useMe() {
  const api = useApiClient();
  return useQuery({
    queryKey: QK_ME,
    queryFn: () => api.request<UserOut>("/v1/me"),
  });
}
