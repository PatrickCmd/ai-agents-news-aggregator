// web/lib/types/api.ts
//
// Hand-written TypeScript types mirroring the backend's Pydantic models
// (see packages/schemas/src/news_schemas/{user_profile,digest,audit}.py).
//
// Future #6 task: auto-generate from the API's OpenAPI schema using
// openapi-typescript. For v1, hand-written keeps the dep tree small.

// ─── UserProfile ────────────────────────────────────────────────────────────

export interface Interests {
  primary: string[];
  secondary: string[];
  specific_topics: string[];
}

export interface Preferences {
  content_type: string[];
  avoid: string[];
}

export interface ReadingTime {
  daily_limit: string;
  preferred_article_count: string;
}

export interface UserProfile {
  background: string[];
  interests: Interests;
  preferences: Preferences;
  goals: string[];
  reading_time: ReadingTime;
}

export interface UserOut {
  id: string; // UUID
  clerk_user_id: string;
  email: string;
  name: string;
  email_name: string;
  profile: UserProfile;
  profile_completed_at: string | null; // ISO timestamp
  created_at: string;
  updated_at: string;
}

// ─── Digest ─────────────────────────────────────────────────────────────────

export type DigestStatus = "pending" | "generated" | "emailed" | "failed";

export interface RankedArticle {
  article_id: number;
  score: number; // 0-100
  title: string;
  url: string;
  summary: string;
  why_ranked: string;
}

export interface DigestSummaryOut {
  id: number;
  user_id: string;
  period_start: string;
  period_end: string;
  intro: string | null;
  top_themes: string[];
  article_count: number;
  status: DigestStatus;
  generated_at: string;
}

export interface DigestOut extends DigestSummaryOut {
  ranked_articles: RankedArticle[];
  error_message: string | null;
}

export interface DigestListResponse {
  items: DigestSummaryOut[];
  next_before: number | null;
}

// ─── Remix ──────────────────────────────────────────────────────────────────

export interface RemixResponse {
  execution_arn: string;
  started_at: string;
}

// ─── Errors ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
  ) {
    super(`API ${status}: ${body.slice(0, 200)}`);
    this.name = "ApiError";
  }
}
