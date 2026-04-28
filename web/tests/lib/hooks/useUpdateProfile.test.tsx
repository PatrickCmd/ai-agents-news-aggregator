import { describe, expect, it } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useUpdateProfile } from "@/lib/hooks/useUpdateProfile";
import { useMe } from "@/lib/hooks/useMe";
import { EMPTY_PROFILE } from "@/lib/constants";

function wrapperFactory() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useUpdateProfile", () => {
  it("PUTs the profile and updates the /me cache via setQueryData", async () => {
    const newProfile = {
      ...EMPTY_PROFILE,
      background: ["AI engineer"],
    };

    server.use(
      http.put("http://localhost:8000/v1/me/profile", async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({
          id: "00000000-0000-4000-8000-000000000001",
          clerk_user_id: "user_test",
          email: "test@example.com",
          name: "Test User",
          email_name: "Test",
          profile: body,
          profile_completed_at: "2026-04-28T11:00:00Z",
          created_at: "2026-04-28T10:00:00Z",
          updated_at: "2026-04-28T11:00:00Z",
        });
      }),
    );

    const { Wrapper, qc } = wrapperFactory();

    // Pre-warm /me cache.
    const { result: meBefore } = renderHook(() => useMe(), { wrapper: Wrapper });
    await waitFor(() => expect(meBefore.current.isSuccess).toBe(true));

    const { result: mut } = renderHook(() => useUpdateProfile(), { wrapper: Wrapper });

    await act(async () => {
      await mut.current.mutateAsync(newProfile);
    });

    // The /me query should now reflect the new profile + completed timestamp.
    const cached = qc.getQueryData<{ profile: typeof newProfile; profile_completed_at: string | null }>(["me"]);
    expect(cached?.profile.background).toEqual(["AI engineer"]);
    expect(cached?.profile_completed_at).not.toBeNull();
  });
});
