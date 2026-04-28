import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMe } from "@/lib/hooks/useMe";
import { MOCK_USER_OUT } from "../../mocks/handlers";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMe", () => {
  it("fetches GET /v1/me and returns UserOut", async () => {
    const { result } = renderHook(() => useMe(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.email).toBe("test@example.com");
    expect(result.current.data?.profile_completed_at).toBeNull();
  });

  it("returns the same UserOut shape from MSW handler", async () => {
    const { result } = renderHook(() => useMe(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual(MOCK_USER_OUT);
  });
});
