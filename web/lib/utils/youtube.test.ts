import { describe, it, expect } from "vitest";
import { youtubeIdFromUrl } from "@/lib/utils/youtube";

describe("youtubeIdFromUrl", () => {
  it("extracts id from youtube.com/watch?v=", () => {
    expect(youtubeIdFromUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
  });

  it("extracts id from youtube.com/watch with extra params", () => {
    expect(
      youtubeIdFromUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PL123"),
    ).toBe("dQw4w9WgXcQ");
  });

  it("extracts id from youtu.be short link", () => {
    expect(youtubeIdFromUrl("https://youtu.be/dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
  });

  it("extracts id from youtu.be with timestamp", () => {
    expect(youtubeIdFromUrl("https://youtu.be/dQw4w9WgXcQ?t=120")).toBe("dQw4w9WgXcQ");
  });

  it("extracts id from /shorts/ path", () => {
    expect(youtubeIdFromUrl("https://www.youtube.com/shorts/dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
  });

  it("extracts id from /embed/ path", () => {
    expect(youtubeIdFromUrl("https://www.youtube.com/embed/dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
  });

  it("returns null for non-YouTube hosts", () => {
    expect(youtubeIdFromUrl("https://vimeo.com/123456")).toBeNull();
    expect(youtubeIdFromUrl("https://example.com/watch?v=dQw4w9WgXcQ")).toBeNull();
  });

  it("returns null for malformed URLs", () => {
    expect(youtubeIdFromUrl("not-a-url")).toBeNull();
    expect(youtubeIdFromUrl("")).toBeNull();
  });

  it("returns null for YouTube URLs without an id", () => {
    expect(youtubeIdFromUrl("https://www.youtube.com/")).toBeNull();
    expect(youtubeIdFromUrl("https://www.youtube.com/watch")).toBeNull();
  });

  it("rejects ids with bad length / chars", () => {
    expect(youtubeIdFromUrl("https://youtu.be/short")).toBeNull();
    expect(youtubeIdFromUrl("https://youtu.be/has spaces in it")).toBeNull();
  });
});
