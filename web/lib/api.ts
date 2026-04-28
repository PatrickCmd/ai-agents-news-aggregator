"use client";

import { useAuth } from "@clerk/clerk-react";
import { ApiError } from "@/lib/types/api";

export interface ApiClient {
  request<T>(path: string, init?: RequestInit): Promise<T>;
}

/**
 * React hook that returns an API client wired to the current Clerk session.
 * Each request mints a fresh JWT via `getToken({ template: "news-api" })`,
 * which adds email + name claims for our backend's ClerkClaims schema.
 *
 * Throws `ApiError(status, body)` on non-2xx responses; callers should let
 * TanStack Query catch the error and surface it through query state.
 */
export function useApiClient(): ApiClient {
  const { getToken } = useAuth();

  return {
    async request<T>(path: string, init?: RequestInit): Promise<T> {
      const token = await getToken({ template: "news-api" });
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...((init?.headers as Record<string, string>) ?? {}),
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const url = `${process.env.NEXT_PUBLIC_API_URL}${path}`;
      const resp = await fetch(url, { ...init, headers });

      if (!resp.ok) {
        const body = await resp.text();
        throw new ApiError(resp.status, body);
      }
      return (await resp.json()) as T;
    },
  };
}
