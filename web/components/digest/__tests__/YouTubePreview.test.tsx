import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { YouTubePreview } from "@/components/digest/YouTubePreview";

describe("<YouTubePreview />", () => {
  it("renders a privacy-enhanced iframe pointing at the right id", () => {
    render(<YouTubePreview videoId="dQw4w9WgXcQ" title="Never gonna" />);
    const iframe = screen.getByTitle("Never gonna") as HTMLIFrameElement;
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe.src).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    expect(iframe.getAttribute("loading")).toBe("lazy");
    const allow = iframe.getAttribute("allow") ?? "";
    expect(allow).toContain("encrypted-media");
    expect(allow).toContain("picture-in-picture");
  });

  it("renders an Open on YouTube escape link", () => {
    render(<YouTubePreview videoId="dQw4w9WgXcQ" title="Never gonna" />);
    const link = screen.getByRole("link", { name: /open on youtube/i }) as HTMLAnchorElement;
    expect(link.href).toBe("https://youtu.be/dQw4w9WgXcQ");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noopener");
    expect(link.rel).toContain("noreferrer");
  });
});
