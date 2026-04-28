import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DigestCard } from "@/components/digest/DigestCard";
import type { DigestSummaryOut } from "@/lib/types/api";

const sample: DigestSummaryOut = {
  id: 17,
  user_id: "00000000-0000-4000-8000-000000000001",
  period_start: "2026-04-27T00:00:00Z",
  period_end: "2026-04-28T00:00:00Z",
  intro: "Today's roundup of agent news",
  top_themes: ["agents", "infra"],
  article_count: 7,
  status: "generated",
  generated_at: "2026-04-28T05:00:00Z",
};

describe("DigestCard", () => {
  it("renders intro, themes, and article count", () => {
    render(<DigestCard digest={sample} />);
    expect(screen.getByText("Today's roundup of agent news")).toBeInTheDocument();
    expect(screen.getByText("agents")).toBeInTheDocument();
    expect(screen.getByText("infra")).toBeInTheDocument();
    expect(screen.getByText(/7 articles/i)).toBeInTheDocument();
  });

  it("links to /digest?id={id}", () => {
    render(<DigestCard digest={sample} />);
    const link = screen.getByRole("link", { name: /read/i });
    expect(link).toHaveAttribute("href", "/digest?id=17");
  });

  it("handles null intro gracefully", () => {
    render(<DigestCard digest={{ ...sample, intro: null }} />);
    expect(screen.getByText(/7 articles/i)).toBeInTheDocument();
  });
});
