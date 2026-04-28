import { describe, expect, it, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRemix } from "@/lib/hooks/useRemix";

function wrapperFactory() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useRemix", () => {
  it("POSTs /v1/remix and resolves with execution_arn", async () => {
    const { Wrapper } = wrapperFactory();
    const { result } = renderHook(() => useRemix(), { wrapper: Wrapper });

    let response;
    await act(async () => {
      response = await result.current.mutateAsync(24);
    });

    expect(response).toMatchObject({
      execution_arn: expect.stringContaining("news-remix-user-dev"),
    });
  });

  it("invalidates ['digests'] queries every 5s for 120s after success", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { Wrapper, qc } = wrapperFactory();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useRemix(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync(24);
    });

    // First 5s tick → 1 invalidation
    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["digests"] });
    const callCountAt5s = invalidateSpy.mock.calls.length;
    expect(callCountAt5s).toBeGreaterThanOrEqual(1);

    // Advance to 120s total → ~24 invalidations
    await act(async () => {
      vi.advanceTimersByTime(115_000);
    });
    expect(invalidateSpy.mock.calls.length).toBeGreaterThanOrEqual(20);

    // After 125s, polling should stop — no more invalidations.
    const callCountAt125s = invalidateSpy.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(invalidateSpy.mock.calls.length).toBe(callCountAt125s);
  });
});
