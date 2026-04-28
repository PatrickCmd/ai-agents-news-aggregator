import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RootPage from "@/app/page";

const useAuthMock = vi.fn();
vi.mock("@clerk/react", () => ({
  useAuth: () => useAuthMock(),
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/hooks/useDigests", () => ({
  useDigestsList: () => ({ data: { pages: [{ items: [] }] }, isLoading: false, hasNextPage: false, dataUpdatedAt: 0 }),
}));
vi.mock("@/lib/hooks/useRemix", () => ({
  useRemix: () => ({ mutate: vi.fn(), isPending: false }),
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

describe("Root page (/) auth branch", () => {
  beforeEach(() => useAuthMock.mockReset());

  it("renders <LandingHero /> when not signed in", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: false });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /one thing you should read today/i }),
    ).toBeInTheDocument();
  });

  it("renders DigestListSection when signed in", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: true });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /your digests/i }),
    ).toBeInTheDocument();
  });

  it("renders a small skeleton while Clerk is loading", () => {
    useAuthMock.mockReturnValue({ isLoaded: false, isSignedIn: false });
    render(wrap(<RootPage />));
    expect(screen.getByTestId("root-skeleton")).toBeInTheDocument();
  });
});
