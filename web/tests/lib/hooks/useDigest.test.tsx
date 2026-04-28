import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useDigest } from "@/lib/hooks/useDigest";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useDigest", () => {
  it("fetches GET /v1/digests/:id", async () => {
    const { result } = renderHook(() => useDigest(42), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(42);
  });

  it("surfaces 404 as a query error", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests/999", () =>
        HttpResponse.json({ detail: "digest not found" }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useDigest(999), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as unknown as { status: number }).status).toBe(404);
  });
});
