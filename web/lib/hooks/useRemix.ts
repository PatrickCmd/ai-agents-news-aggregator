"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useApiClient } from "@/lib/api";
import { ApiError, type RemixResponse } from "@/lib/types/api";

const POLL_INTERVAL_MS = 5_000;
const POLL_DURATION_MS = 120_000;

export function useRemix() {
  const api = useApiClient();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (lookback_hours: number = 24): Promise<RemixResponse> =>
      api.request<RemixResponse>("/v1/remix", {
        method: "POST",
        body: JSON.stringify({ lookback_hours }),
      }),
    onSuccess: () => {
      toast.success("Your remix is on the way (~30-60s)");
      // Poll the digest list every 5s for 120s. invalidateQueries triggers
      // refetch on whatever's mounted; if user navigates away, no-op.
      let elapsed = 0;
      const interval = setInterval(() => {
        elapsed += POLL_INTERVAL_MS;
        qc.invalidateQueries({ queryKey: ["digests"] });
        if (elapsed >= POLL_DURATION_MS) clearInterval(interval);
      }, POLL_INTERVAL_MS);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          toast.error("Complete your profile to remix");
          return;
        }
        if (err.status === 503) {
          toast.error("Service busy — try again in a moment");
          return;
        }
      }
      toast.error("Remix failed — see logs");
    },
  });
}
