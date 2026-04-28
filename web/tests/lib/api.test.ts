import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { useApiClient } from "@/lib/api";

describe("useApiClient", () => {
  it("injects Authorization: Bearer <token> from getToken({template: 'news-api'})", async () => {
    let capturedAuth = "";
    server.use(
      http.get("http://localhost:8000/v1/me", ({ request }) => {
        capturedAuth = request.headers.get("authorization") ?? "";
        return HttpResponse.json({ ok: true });
      }),
    );

    const { result } = renderHook(() => useApiClient());
    await act(async () => {
      await result.current.request("/v1/me");
    });

    expect(capturedAuth).toBe("Bearer test-jwt-token");
  });

  it("throws ApiError(status, body) on non-2xx", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests", () =>
        HttpResponse.text("server exploded", { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useApiClient());
    await expect(result.current.request("/v1/digests")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      body: "server exploded",
    });
  });

  it("parses JSON responses on 2xx", async () => {
    server.use(
      http.get("http://localhost:8000/v1/me", () =>
        HttpResponse.json({ id: "abc", email: "x@y.com" }),
      ),
    );

    const { result } = renderHook(() => useApiClient());
    const data = await result.current.request<{ id: string; email: string }>("/v1/me");
    expect(data).toEqual({ id: "abc", email: "x@y.com" });
  });
});
