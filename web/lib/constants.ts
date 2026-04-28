import type { UserProfile } from "@/lib/types/api";

/**
 * Mirror of the backend's UserProfile.empty() classmethod.
 *
 * Used by the profile editor as the default value for first-time users
 * (whose lazy-upserted user row has an all-empty profile). The shape MUST
 * stay byte-for-byte identical to packages/schemas/src/news_schemas/user_profile.py
 * UserProfile.empty() — drift here breaks the round-trip with PUT /v1/me/profile.
 *
 * The test in tests/lib/userProfile.test.ts asserts this equality.
 */
export const EMPTY_PROFILE: UserProfile = {
  background: [],
  interests: { primary: [], secondary: [], specific_topics: [] },
  preferences: { content_type: [], avoid: [] },
  goals: [],
  reading_time: { daily_limit: "30 minutes", preferred_article_count: "10" },
};
