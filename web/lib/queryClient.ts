"use client";

import { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

/**
 * Singleton QueryClient. Defaults:
 *
 * - 30s staleTime: most reads tolerate brief staleness; reduces refetch chatter.
 * - 1 retry: transient network blips heal on retry; auth errors surface
 *   immediately (TanStack Query doesn't retry 4xx by default).
 * - refetchOnWindowFocus: catch updates when user returns to tab.
 * - mutation onError: surface error message via toast for user-visible feedback.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: true,
      },
      mutations: {
        onError: (err) => {
          if (err instanceof Error) toast.error(err.message);
          else toast.error("Something went wrong");
        },
      },
    },
  });
}
