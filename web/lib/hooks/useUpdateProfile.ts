"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useApiClient } from "@/lib/api";
import { QK_ME } from "@/lib/hooks/useMe";
import type { UserOut, UserProfile } from "@/lib/types/api";

export function useUpdateProfile() {
  const api = useApiClient();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (profile: UserProfile) =>
      api.request<UserOut>("/v1/me/profile", {
        method: "PUT",
        body: JSON.stringify(profile),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(QK_ME, updated);
      toast.success("Profile saved");
    },
  });
}
