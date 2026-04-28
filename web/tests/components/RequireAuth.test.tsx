import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

describe("RequireAuth", () => {
  it("renders skeleton while !isLoaded", async () => {
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: false, isSignedIn: false }),
      RedirectToSignIn: () => <div data-testid="redirect" />,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-skeleton")).toBeInTheDocument();
  });

  it("renders <RedirectToSignIn> when loaded but not signed in", async () => {
    vi.resetModules();
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: true, isSignedIn: false }),
      RedirectToSignIn: () => <div data-testid="redirect" />,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(screen.getByTestId("redirect")).toBeInTheDocument();
  });

  it("renders children when signed in", async () => {
    vi.resetModules();
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: true, isSignedIn: true }),
      RedirectToSignIn: () => null,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.getByText("protected")).toBeInTheDocument();
  });
});
