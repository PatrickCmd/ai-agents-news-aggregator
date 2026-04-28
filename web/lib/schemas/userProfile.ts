import { z } from "zod";

const NonEmptyStringArray = z.array(z.string().min(1)).default([]);

export const UserProfileSchema = z.object({
  background: NonEmptyStringArray,
  interests: z.object({
    primary: NonEmptyStringArray,
    secondary: NonEmptyStringArray,
    specific_topics: NonEmptyStringArray,
  }),
  preferences: z.object({
    content_type: NonEmptyStringArray,
    avoid: NonEmptyStringArray,
  }),
  goals: NonEmptyStringArray,
  reading_time: z.object({
    daily_limit: z.string().min(1).default("30 minutes"),
    preferred_article_count: z.string().min(1).default("10"),
  }),
});

export type UserProfileFromSchema = z.infer<typeof UserProfileSchema>;
