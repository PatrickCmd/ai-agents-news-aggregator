import { describe, expect, it } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useDigestsList } from "@/lib/hooks/useDigests";
import type { DigestListResponse, DigestSummaryOut } from "@/lib/types/api";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const sampleDigest = (id: number): DigestSummaryOut => ({
  id,
  user_id: "00000000-0000-4000-8000-000000000001",
  period_start: "2026-04-27T00:00:00Z",
  period_end: "2026-04-28T00:00:00Z",
  intro: `day ${id}`,
  top_themes: ["agents"],
  article_count: 7,
  status: "generated",
  generated_at: "2026-04-28T05:00:00Z",
});

describe("useDigestsList", () => {
  it("fetches first page", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests", () =>
        HttpResponse.json<DigestListResponse>({
          items: [sampleDigest(5), sampleDigest(4)],
          next_before: 4,
        }),
      ),
    );

    const { result } = renderHook(() => useDigestsList(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const flat = result.current.data?.pages.flatMap((p) => p.items) ?? [];
    expect(flat.map((d) => d.id)).toEqual([5, 4]);
  });

  it("fetchNextPage uses next_before cursor", async () => {
    const calls: string[] = [];
    server.use(
      http.get("http://localhost:8000/v1/digests", ({ request }) => {
        calls.push(new URL(request.url).search);
        const before = new URL(request.url).searchParams.get("before");
        if (before === "3") {
          return HttpResponse.json<DigestListResponse>({
            items: [sampleDigest(2), sampleDigest(1)],
            next_before: null,
          });
        }
        return HttpResponse.json<DigestListResponse>({
          items: [sampleDigest(5), sampleDigest(4), sampleDigest(3)],
          next_before: 3,
        });
      }),
    );

    const { result } = renderHook(() => useDigestsList(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() =>
      expect(
        (result.current.data?.pages.flatMap((p) => p.items) ?? []).map(
          (d) => d.id,
        ),
      ).toEqual([5, 4, 3, 2, 1]),
    );

    const flat = result.current.data?.pages.flatMap((p) => p.items) ?? [];
    expect(flat.map((d) => d.id)).toEqual([5, 4, 3, 2, 1]);
    expect(result.current.hasNextPage).toBe(false);
    expect(calls.some((c) => c.includes("before=3"))).toBe(true);
  });
});
