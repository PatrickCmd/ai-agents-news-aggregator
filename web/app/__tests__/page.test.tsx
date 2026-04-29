import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RootPage from "@/app/page";

const useAuthMock = vi.fn();
vi.mock("@clerk/react", () => ({
  useAuth: () => useAuthMock(),
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const useMeMock = vi.fn();
vi.mock("@/lib/hooks/useMe", () => ({
  useMe: () => useMeMock(),
}));

vi.mock("@/lib/hooks/useDigests", () => ({
  useDigestsList: () => ({
    data: { pages: [{ items: [] }] },
    isLoading: false,
    hasNextPage: false,
    dataUpdatedAt: 0,
  }),
}));
vi.mock("@/lib/hooks/useRemix", () => ({
  useRemix: () => ({ mutate: vi.fn(), isPending: false }),
}));

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  usePathname: () => "/",
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

describe("Root page (/) auth branch", () => {
  beforeEach(() => {
    useAuthMock.mockReset();
    useMeMock.mockReset();
    replaceMock.mockReset();
  });

  it("renders <LandingHero /> when not signed in", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: false });
    useMeMock.mockReturnValue({ data: undefined });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /one thing you should read today/i }),
    ).toBeInTheDocument();
  });

  it("renders DigestListSection when signed in with completed profile", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: true });
    useMeMock.mockReturnValue({
      data: { profile_completed_at: "2026-04-01T00:00:00Z" },
    });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /your digests/i }),
    ).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("redirects to /profile?onboarding=1 when signed in with incomplete profile", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: true });
    useMeMock.mockReturnValue({
      data: { profile_completed_at: null },
    });
    render(wrap(<RootPage />));
    expect(replaceMock).toHaveBeenCalledWith("/profile?onboarding=1");
  });

  it("renders a small skeleton while Clerk is loading", () => {
    useAuthMock.mockReturnValue({ isLoaded: false, isSignedIn: false });
    useMeMock.mockReturnValue({ data: undefined });
    render(wrap(<RootPage />));
    expect(screen.getByTestId("root-skeleton")).toBeInTheDocument();
  });
});
