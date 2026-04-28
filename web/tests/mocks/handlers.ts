import { http, HttpResponse } from "msw";

const API = "http://localhost:8000";

export const MOCK_USER_OUT = {
  id: "00000000-0000-4000-8000-000000000001",
  clerk_user_id: "user_test",
  email: "test@example.com",
  name: "Test User",
  email_name: "Test",
  profile: {
    background: [],
    interests: { primary: [], secondary: [], specific_topics: [] },
    preferences: { content_type: [], avoid: [] },
    goals: [],
    reading_time: { daily_limit: "30 minutes", preferred_article_count: "10" },
  },
  profile_completed_at: null,
  created_at: "2026-04-28T10:00:00Z",
  updated_at: "2026-04-28T10:00:00Z",
};

export const handlers = [
  http.get(`${API}/v1/me`, () => HttpResponse.json(MOCK_USER_OUT)),
  http.put(`${API}/v1/me/profile`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      ...MOCK_USER_OUT,
      profile: body,
      profile_completed_at: "2026-04-28T11:00:00Z",
    });
  }),
  http.get(`${API}/v1/digests`, () =>
    HttpResponse.json({ items: [], next_before: null }),
  ),
  http.get(`${API}/v1/digests/:id`, ({ params }) => {
    return HttpResponse.json({
      id: Number(params.id),
      user_id: MOCK_USER_OUT.id,
      period_start: "2026-04-27T00:00:00Z",
      period_end: "2026-04-28T00:00:00Z",
      intro: "Today's roundup",
      ranked_articles: [],
      top_themes: ["agents", "infra"],
      article_count: 7,
      status: "generated",
      error_message: null,
      generated_at: "2026-04-28T05:00:00Z",
    });
  }),
  http.post(`${API}/v1/remix`, () =>
    HttpResponse.json({
      execution_arn: "arn:aws:states:us-east-1:111:execution:news-remix-user-dev:test",
      started_at: "2026-04-28T11:00:00Z",
    }),
  ),
];
