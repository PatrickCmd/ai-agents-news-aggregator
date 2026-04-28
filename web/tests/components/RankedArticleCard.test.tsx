import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankedArticleCard } from "@/components/digest/RankedArticleCard";
import type { RankedArticle } from "@/lib/types/api";

const article: RankedArticle = {
  article_id: 42,
  score: 87,
  title: "OpenAI ships Agents SDK v3",
  url: "https://openai.com/blog/agents-sdk-v3",
  summary: "Tool calling, structured outputs, and streaming.",
  why_ranked: "Matches your interest in 'agents' (primary) and 'LLMs' (specific_topics).",
};

describe("RankedArticleCard", () => {
  it("renders rank, title, summary, why_ranked, and score badge", () => {
    render(<RankedArticleCard article={article} rank={1} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("OpenAI ships Agents SDK v3")).toBeInTheDocument();
    expect(screen.getByText(/tool calling/i)).toBeInTheDocument();
    expect(screen.getByText(/matches your interest/i)).toBeInTheDocument();
    expect(screen.getByText("87")).toBeInTheDocument();
  });

  it("title links to article URL with target=_blank", () => {
    render(<RankedArticleCard article={article} rank={1} />);
    const link = screen.getByRole("link", { name: "OpenAI ships Agents SDK v3" });
    expect(link).toHaveAttribute("href", article.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
