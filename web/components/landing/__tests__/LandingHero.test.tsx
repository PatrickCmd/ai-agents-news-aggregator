import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LandingHero } from "@/components/landing/LandingHero";

vi.mock("@clerk/react", () => ({
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("<LandingHero />", () => {
  it("renders the hero question", () => {
    render(<LandingHero />);
    expect(
      screen.getByRole("heading", { level: 1, name: /one thing you should read today/i }),
    ).toBeInTheDocument();
  });

  it("renders both CTAs (sign-in primary + how-it-works secondary)", () => {
    render(<LandingHero />);
    expect(screen.getByRole("button", { name: /sign in to read today/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /how it works/i })).toBeInTheDocument();
  });

  it("renders the three how-it-works stages", () => {
    render(<LandingHero />);
    expect(screen.getByText(/we crawl/i)).toBeInTheDocument();
    expect(screen.getByText(/we rank/i)).toBeInTheDocument();
    expect(screen.getByText(/you read/i)).toBeInTheDocument();
  });
});
