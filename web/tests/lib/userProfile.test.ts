import { describe, expect, it } from "vitest";
import { UserProfileSchema } from "@/lib/schemas/userProfile";
import { EMPTY_PROFILE } from "@/lib/constants";
import type { UserProfile } from "@/lib/types/api";

describe("UserProfileSchema", () => {
  it("accepts a fully-populated profile", () => {
    const valid: UserProfile = {
      background: ["AI engineer"],
      interests: {
        primary: ["LLMs"],
        secondary: ["devops"],
        specific_topics: ["MCP"],
      },
      preferences: { content_type: ["blogs"], avoid: ["press releases"] },
      goals: ["stay current"],
      reading_time: { daily_limit: "20 minutes", preferred_article_count: "8" },
    };
    expect(() => UserProfileSchema.parse(valid)).not.toThrow();
  });

  it("rejects empty strings inside array fields", () => {
    const invalid = {
      ...EMPTY_PROFILE,
      interests: { ...EMPTY_PROFILE.interests, primary: [""] },
    };
    expect(() => UserProfileSchema.parse(invalid)).toThrow();
  });

  it("EMPTY_PROFILE parses cleanly through the schema", () => {
    expect(() => UserProfileSchema.parse(EMPTY_PROFILE)).not.toThrow();
  });

  it("EMPTY_PROFILE matches the backend's UserProfile.empty() shape", () => {
    expect(EMPTY_PROFILE).toEqual({
      background: [],
      interests: { primary: [], secondary: [], specific_topics: [] },
      preferences: { content_type: [], avoid: [] },
      goals: [],
      reading_time: { daily_limit: "30 minutes", preferred_article_count: "10" },
    });
  });
});
