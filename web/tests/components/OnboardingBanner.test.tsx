import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { OnboardingBanner } from "@/components/auth/OnboardingBanner";

describe("OnboardingBanner", () => {
  it("renders welcome copy", () => {
    render(<OnboardingBanner />);
    expect(screen.getByText(/welcome/i)).toBeInTheDocument();
    expect(screen.getByText(/complete your profile/i)).toBeInTheDocument();
  });
});
