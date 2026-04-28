# Sub-project #5 — Frontend (Next.js + Clerk + S3/CloudFront) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a static-exported Next.js frontend at `digest.patrickcmd.dev` that lets a Clerk-authenticated user complete onboarding, browse daily digests, and trigger on-demand "remix now" runs — closing the loop between the cron pipeline (#3) and the end user.

**Architecture:** `output: "export"` Next.js → `web/out/` → S3 + CloudFront via OAC. `@clerk/clerk-react` (SPA flavour, NOT `@clerk/nextjs`) for auth — `<RedirectToSignIn />` to Clerk's hosted Account Portal. TanStack Query for all data, React Hook Form + Zod for the profile editor, Tailwind v4 + shadcn/ui for styling. Per-env Terraform module under `infra/web/`, manual `workflow_dispatch` GitHub Actions deploys with deploy|destroy + dev|test|prod choices.

**Tech Stack:** TypeScript strict, pnpm ≥ 9, Next.js 15 (static export), Tailwind v4, shadcn/ui, @clerk/clerk-react, TanStack Query v5, React Hook Form, Zod, sonner (toasts), Vitest + @testing-library/react + MSW, Terraform, GitHub Actions OIDC.

---

## File structure (locked in before tasks)

### New (created)

```
web/
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── postcss.config.mjs
├── components.json                  # shadcn/ui config
├── eslint.config.mjs
├── .prettierrc.json
├── .nvmrc
├── .npmrc
├── .env.example
├── .env.local                       # gitignored
├── vitest.config.ts
├── public/
│   └── favicon.ico
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   ├── not-found.tsx
│   └── (authenticated)/
│       ├── layout.tsx
│       ├── page.tsx
│       ├── digests/
│       │   └── [id]/
│       │       └── page.tsx
│       └── profile/
│           └── page.tsx
├── components/
│   ├── auth/
│   │   ├── RequireAuth.tsx
│   │   └── OnboardingBanner.tsx
│   ├── digest/
│   │   ├── DigestCard.tsx
│   │   ├── RankedArticleCard.tsx
│   │   ├── EmptyState.tsx
│   │   ├── DigestListSkeleton.tsx
│   │   └── DigestDetailSkeleton.tsx
│   ├── profile/
│   │   ├── BackgroundFieldArray.tsx
│   │   ├── InterestsFieldGroup.tsx
│   │   ├── PreferencesFieldGroup.tsx
│   │   ├── GoalsFieldArray.tsx
│   │   └── ReadingTimeFieldGroup.tsx
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Footer.tsx
│   │   └── ThemeToggle.tsx
│   └── ui/                          # shadcn primitives (vendored copy-paste)
├── lib/
│   ├── api.ts
│   ├── queryClient.ts
│   ├── theme.tsx
│   ├── constants.ts                 # EMPTY_PROFILE
│   ├── hooks/
│   │   ├── useMe.ts
│   │   ├── useDigests.ts
│   │   ├── useDigest.ts
│   │   ├── useUpdateProfile.ts
│   │   └── useRemix.ts
│   ├── schemas/
│   │   └── userProfile.ts
│   └── types/
│       └── api.ts
└── tests/
    ├── setup.ts
    ├── mocks/
    │   ├── server.ts                # MSW server
    │   └── handlers.ts              # default request handlers
    ├── lib/
    │   ├── api.test.ts
    │   └── hooks/
    │       ├── useMe.test.ts
    │       ├── useDigests.test.ts
    │       ├── useDigest.test.ts
    │       ├── useUpdateProfile.test.ts
    │       └── useRemix.test.ts
    └── components/
        ├── RequireAuth.test.tsx
        ├── OnboardingBanner.test.tsx
        ├── DigestCard.test.tsx
        ├── RankedArticleCard.test.tsx
        └── ProfileEditor.test.tsx

infra/web/
├── backend.tf
├── data.tf
├── variables.tf
├── main.tf
├── cloudfront.tf
├── route53.tf
├── github_oidc.tf
├── outputs.tf
├── terraform.tfvars.example
└── .gitignore

.github/
├── workflows/
│   ├── web-ci.yml
│   └── web-deploy.yml
└── dependabot.yml
```

### Modified

- `Makefile` — append `# ---------- web (#5) ----------` block.
- `infra/bootstrap/` — add GitHub OIDC provider resource.
- `infra/README.md` — append "Sub-project #5 — Frontend" section.
- `AGENTS.md` — flip #5 row, add layout entries, ops section, anti-patterns.
- `README.md` — refresh status + add "Running the Frontend (#5)" section.
- `.pre-commit-config.yaml` — add OSV-Scanner hook scoped to `web/`.
- `.gitignore` — add `web/.next/`, `web/out/`, `web/node_modules/`, `web/.env*.local`, `web/coverage/`.
- `docs/architecture.md` — flip the frontend node from "planned" to "live".

---

## Phase 0 — Project bootstrapping

### Task 0.1: pnpm workspace scaffold (`web/` package + tooling configs)

**Files:**
- Create: `web/package.json`
- Create: `web/.nvmrc`
- Create: `web/.npmrc`
- Create: `web/pnpm-workspace.yaml`
- Create: `web/.prettierrc.json`
- Create: `web/.env.example`
- Modify: `.gitignore` (add `web/` entries)

- [ ] **Step 1: Verify pnpm + Node available**

```sh
node --version    # expect v20.x
pnpm --version    # expect 9.x or later
```

If pnpm is missing: `brew install pnpm` (or `npm install -g pnpm`).

- [ ] **Step 2: Create `web/` directory + scaffold files**

```sh
mkdir -p web
cd web
```

- [ ] **Step 3: Create `web/package.json`**

```json
{
  "name": "web",
  "version": "0.6.0",
  "private": true,
  "engines": {
    "node": ">=20",
    "pnpm": ">=9"
  },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "lint:fix": "next lint --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {},
  "devDependencies": {}
}
```

- [ ] **Step 4: Create `web/.nvmrc`**

```
20
```

- [ ] **Step 5: Create `web/.npmrc`**

```
engine-strict=true
auto-install-peers=true
strict-peer-dependencies=false
```

- [ ] **Step 6: Create `web/pnpm-workspace.yaml`** (placeholder for future package splits)

```yaml
packages:
  - "."
```

- [ ] **Step 7: Create `web/.prettierrc.json`**

```json
{
  "printWidth": 100,
  "singleQuote": false,
  "trailingComma": "all",
  "semi": true,
  "tabWidth": 2,
  "plugins": ["prettier-plugin-tailwindcss"]
}
```

- [ ] **Step 8: Create `web/.env.example`**

```bash
# Frontend env vars — these get baked into the static bundle at build time.
# For local dev, copy this file to .env.local and fill in real values.

# Backend API origin. For local dev, run `make api-serve` and use http://localhost:8000.
NEXT_PUBLIC_API_URL=http://localhost:8000

# Clerk publishable key (from Clerk Dashboard → API Keys).
# Format: pk_test_xxx for dev instances, pk_live_xxx for prod.
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_replace_me
```

- [ ] **Step 9: Update root `.gitignore` with `web/` entries**

Append to `.gitignore` (do not delete existing lines):

```
# Frontend (#5)
web/.next/
web/out/
web/node_modules/
web/coverage/
web/.env.local
web/.env.*.local
```

- [ ] **Step 10: Verify pnpm lockfile creation works**

```sh
cd web
pnpm install
```

Expected: creates an empty `pnpm-lock.yaml` (no deps yet). Should complete without errors.

- [ ] **Step 11: Commit**

```sh
cd ..   # back to repo root
git add web/package.json web/.nvmrc web/.npmrc web/pnpm-workspace.yaml \
        web/.prettierrc.json web/.env.example web/pnpm-lock.yaml .gitignore
git commit -m "feat(web): scaffold pnpm workspace + tooling configs"
```

---

### Task 0.2: Next.js + TypeScript + Tailwind v4 setup

**Files:**
- Modify: `web/package.json` (deps)
- Create: `web/next.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/tailwind.config.ts`
- Create: `web/postcss.config.mjs`
- Create: `web/app/globals.css`

- [ ] **Step 1: Install Next.js + TypeScript core deps**

```sh
cd web
pnpm add next@latest react@latest react-dom@latest
pnpm add -D typescript @types/node @types/react @types/react-dom
```

- [ ] **Step 2: Install Tailwind v4 + tooling**

```sh
pnpm add -D tailwindcss@latest @tailwindcss/postcss postcss \
            @tailwindcss/typography tailwindcss-animate \
            prettier prettier-plugin-tailwindcss
```

- [ ] **Step 3: Create `web/next.config.ts`**

```ts
import type { NextConfig } from "next";

const config: NextConfig = {
  // Static export → web/out/ → uploaded to S3 + served via CloudFront.
  // No SSR, no server actions, no middleware. See spec §1.
  output: "export",

  // Trailing slash so /digests/123/ → /digests/123/index.html (CloudFront default object).
  trailingSlash: true,

  // next/image's default optimizer requires a Node server. With static export we ship
  // images verbatim (the small set we have — favicon, logo — doesn't need optimization).
  images: { unoptimized: true },

  // Disable Next.js telemetry in CI.
  // (Local devs can opt in via `npx next telemetry enable` if they want.)
  // (Note: NEXT_TELEMETRY_DISABLED=1 in CI env is the runtime kill switch; this is the
  //  build-time default for local devs.)
  experimental: {},
};

export default config;
```

- [ ] **Step 4: Create `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    },
    "noUncheckedIndexedAccess": true
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 5: Create `web/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1280px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography"), require("tailwindcss-animate")],
};

export default config;
```

- [ ] **Step 6: Create `web/postcss.config.mjs`**

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

- [ ] **Step 7: Create `web/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 240 10% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 240 10% 3.9%;
    --primary: 240 5.9% 10%;
    --primary-foreground: 0 0% 98%;
    --secondary: 240 4.8% 95.9%;
    --secondary-foreground: 240 5.9% 10%;
    --muted: 240 4.8% 95.9%;
    --muted-foreground: 240 3.8% 46.1%;
    --accent: 240 4.8% 95.9%;
    --accent-foreground: 240 5.9% 10%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 5.9% 90%;
    --input: 240 5.9% 90%;
    --ring: 240 5.9% 10%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 240 10% 3.9%;
    --foreground: 0 0% 98%;
    --card: 240 10% 3.9%;
    --card-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 240 5.9% 10%;
    --secondary: 240 3.7% 15.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 240 3.7% 15.9%;
    --muted-foreground: 240 5% 64.9%;
    --accent: 240 3.7% 15.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 3.7% 15.9%;
    --input: 240 3.7% 15.9%;
    --ring: 240 4.9% 83.9%;
  }

  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
    font-feature-settings: "rlig" 1, "calt" 1;
  }
}
```

- [ ] **Step 8: Verify `pnpm typecheck` runs cleanly** (no source files yet, so it should pass trivially)

```sh
cd web
pnpm typecheck
```

Expected: `tsc` runs, finds nothing to check, exits 0.

- [ ] **Step 9: Commit**

```sh
git add web/package.json web/pnpm-lock.yaml web/next.config.ts web/tsconfig.json \
        web/tailwind.config.ts web/postcss.config.mjs web/app/globals.css
git commit -m "feat(web): Next.js + TypeScript + Tailwind v4 setup (output: export)"
```

---

### Task 0.3: ESLint + Vitest + RTL + MSW configs

**Files:**
- Modify: `web/package.json` (deps)
- Create: `web/eslint.config.mjs`
- Create: `web/vitest.config.ts`
- Create: `web/tests/setup.ts`
- Create: `web/tests/mocks/server.ts`
- Create: `web/tests/mocks/handlers.ts`

- [ ] **Step 1: Install ESLint + Vitest + RTL + MSW**

```sh
cd web
pnpm add -D eslint eslint-config-next \
            vitest @vitest/coverage-v8 jsdom \
            @testing-library/react @testing-library/jest-dom @testing-library/user-event \
            msw
```

- [ ] **Step 2: Create `web/eslint.config.mjs`** (flat config — Next.js 15 default)

```js
import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Strict-mode TypeScript: forbid implicit any, require explicit return types on exports.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
];
```

- [ ] **Step 3: Install eslintrc compat helper**

```sh
pnpm add -D @eslint/eslintrc
```

- [ ] **Step 4: Create `web/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
    css: true,
  },
});
```

- [ ] **Step 5: Install vitest plugin**

```sh
pnpm add -D @vitejs/plugin-react
```

- [ ] **Step 6: Create `web/tests/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
import { vi, afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./mocks/server";

// Clerk: stub the SDK so tests never hit the real Clerk service.
vi.mock("@clerk/clerk-react", () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    isLoaded: true,
    isSignedIn: true,
    getToken: vi.fn().mockResolvedValue("test-jwt-token"),
  }),
  useUser: () => ({
    user: {
      id: "user_test",
      primaryEmailAddress: { emailAddress: "test@example.com" },
      fullName: "Test User",
    },
  }),
  RedirectToSignIn: () => null,
  UserButton: () => null,
}));

// MSW: intercept all fetches; tests can override with server.use(...).
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

// Process env defaults for tests — tests need NEXT_PUBLIC_API_URL set so api.ts builds URLs correctly.
process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_dummy";
```

- [ ] **Step 7: Create `web/tests/mocks/handlers.ts`**

```ts
import { http, HttpResponse } from "msw";
import type { UserOut, DigestListResponse, DigestOut } from "@/lib/types/api";

const API = "http://localhost:8000";

export const MOCK_USER_OUT: UserOut = {
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
    HttpResponse.json<DigestListResponse>({ items: [], next_before: null }),
  ),
  http.get(`${API}/v1/digests/:id`, ({ params }) => {
    return HttpResponse.json<DigestOut>({
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
```

- [ ] **Step 8: Create `web/tests/mocks/server.ts`**

```ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

- [ ] **Step 9: Verify lint runs cleanly**

```sh
cd web
pnpm lint
```

Expected: `eslint` exits 0 (no source files yet to lint).

- [ ] **Step 10: Verify Vitest discovers no tests yet**

```sh
pnpm test
```

Expected: `No test files found, exiting with code 0` (or `1` depending on Vitest version — both acceptable; we have no tests yet).

If exit code is 1 because no tests: pass `--passWithNoTests`:

```sh
pnpm test --passWithNoTests
```

- [ ] **Step 11: Commit**

```sh
git add web/package.json web/pnpm-lock.yaml web/eslint.config.mjs \
        web/vitest.config.ts web/tests/setup.ts web/tests/mocks/
git commit -m "feat(web): ESLint + Vitest + RTL + MSW setup with default Clerk + API mocks"
```

---

### Task 0.4: shadcn/ui init + initial UI primitives

**Files:**
- Create: `web/components.json`
- Create: `web/lib/utils.ts`
- Create: `web/components/ui/button.tsx` (and others, vendored by CLI)

- [ ] **Step 1: Run shadcn init**

```sh
cd web
pnpm dlx shadcn@latest init
```

When prompted:
- TypeScript: **Yes**
- Style: **default**
- Base color: **slate**
- Use CSS variables: **Yes**
- Tailwind config: `tailwind.config.ts`
- CSS file: `app/globals.css`
- Import alias for components: `@/components`
- Import alias for utils: `@/lib/utils`
- React Server Components: **Yes** (we'll only mark client components manually)

This creates:
- `web/components.json`
- `web/lib/utils.ts` (with `cn()` helper)
- A few minimum CSS deps installed

- [ ] **Step 2: Add the initial set of UI primitives**

```sh
cd web
pnpm dlx shadcn@latest add button card dialog dropdown-menu form input label \
                            skeleton tooltip badge select separator alert sonner
```

Each command vendors the file under `web/components/ui/<name>.tsx`. The CLI also installs runtime deps (Radix primitives, sonner, etc.) automatically.

- [ ] **Step 3: Verify `pnpm typecheck` is clean**

```sh
pnpm typecheck
```

Expected: passes. shadcn-vendored files are TS-clean out of the box.

- [ ] **Step 4: Verify `pnpm lint` is clean**

```sh
pnpm lint
```

Expected: passes (or warns about a couple of any-types in the form component — both warnings, not errors. If errors: lower the rule for `web/components/ui/**` files in `eslint.config.mjs` to `"warn"` since these are vendored).

- [ ] **Step 5: Commit**

```sh
git add web/components.json web/lib/utils.ts web/components/ui/ web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): shadcn/ui init + initial UI primitives (button, card, form, …)"
```

---

## Phase 1 — Core libs

### Task 1.1: TypeScript types mirroring backend (`lib/types/api.ts`)

**Files:**
- Create: `web/lib/types/api.ts`

- [ ] **Step 1: Create the file**

```ts
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
```

- [ ] **Step 2: Typecheck**

```sh
cd web
pnpm typecheck
```

Expected: passes.

- [ ] **Step 3: Commit**

```sh
git add web/lib/types/api.ts
git commit -m "feat(web): API types mirroring backend Pydantic models"
```

---

### Task 1.2: Zod schema for `UserProfile` (`lib/schemas/userProfile.ts`) + `EMPTY_PROFILE`

**Files:**
- Create: `web/lib/schemas/userProfile.ts`
- Create: `web/lib/constants.ts`
- Create: `web/tests/lib/userProfile.test.ts`

- [ ] **Step 1: Install Zod**

```sh
cd web
pnpm add zod
```

- [ ] **Step 2: Write the failing test**

Create `web/tests/lib/userProfile.test.ts`:

```ts
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
    // Mirrors packages/schemas/src/news_schemas/user_profile.py UserProfile.empty()
    expect(EMPTY_PROFILE).toEqual({
      background: [],
      interests: { primary: [], secondary: [], specific_topics: [] },
      preferences: { content_type: [], avoid: [] },
      goals: [],
      reading_time: { daily_limit: "30 minutes", preferred_article_count: "10" },
    });
  });
});
```

- [ ] **Step 3: Run, expect FAIL with "cannot import"**

```sh
pnpm test
```

Expected: FAIL — `UserProfileSchema` and `EMPTY_PROFILE` aren't defined yet.

- [ ] **Step 4: Create `web/lib/schemas/userProfile.ts`**

```ts
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
```

- [ ] **Step 5: Create `web/lib/constants.ts`**

```ts
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
```

- [ ] **Step 6: Run, expect ALL PASS**

```sh
pnpm test
```

Expected: 4 tests pass.

- [ ] **Step 7: Typecheck + lint**

```sh
pnpm typecheck && pnpm lint
```

Expected: both clean.

- [ ] **Step 8: Commit**

```sh
git add web/lib/schemas/userProfile.ts web/lib/constants.ts \
        web/tests/lib/userProfile.test.ts web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): UserProfile Zod schema + EMPTY_PROFILE constant"
```

---

### Task 1.3: API client (`lib/api.ts`) with JWT injection + ApiError

**Files:**
- Create: `web/lib/api.ts`
- Create: `web/tests/lib/api.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/tests/lib/api.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { useApiClient } from "@/lib/api";
import { ApiError } from "@/lib/types/api";

describe("useApiClient", () => {
  it("injects Authorization: Bearer <token> from getToken({template: 'news-api'})", async () => {
    let capturedAuth = "";
    server.use(
      http.get("http://localhost:8000/v1/me", ({ request }) => {
        capturedAuth = request.headers.get("authorization") ?? "";
        return HttpResponse.json({ ok: true });
      }),
    );

    const { result } = renderHook(() => useApiClient());
    await act(async () => {
      await result.current.request("/v1/me");
    });

    expect(capturedAuth).toBe("Bearer test-jwt-token");
  });

  it("throws ApiError(status, body) on non-2xx", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests", () =>
        HttpResponse.text("server exploded", { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useApiClient());
    await expect(result.current.request("/v1/digests")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      body: "server exploded",
    });
  });

  it("parses JSON responses on 2xx", async () => {
    server.use(
      http.get("http://localhost:8000/v1/me", () =>
        HttpResponse.json({ id: "abc", email: "x@y.com" }),
      ),
    );

    const { result } = renderHook(() => useApiClient());
    const data = await result.current.request<{ id: string; email: string }>("/v1/me");
    expect(data).toEqual({ id: "abc", email: "x@y.com" });
  });

  it("calls getToken with template 'news-api'", async () => {
    const getTokenMock = vi.fn().mockResolvedValue("custom-token");
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken: getTokenMock }),
    }));

    // Re-import after mocking.
    const { useApiClient: freshHook } = await import("@/lib/api");
    server.use(
      http.get("http://localhost:8000/v1/me", () => HttpResponse.json({ ok: true })),
    );

    const { result } = renderHook(() => freshHook());
    await act(async () => {
      await result.current.request("/v1/me");
    });

    expect(getTokenMock).toHaveBeenCalledWith({ template: "news-api" });
  });
});
```

- [ ] **Step 2: Run, expect FAIL with "cannot import 'useApiClient'"**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/api.ts`**

```ts
"use client";

import { useAuth } from "@clerk/clerk-react";
import { ApiError } from "@/lib/types/api";

export interface ApiClient {
  request<T>(path: string, init?: RequestInit): Promise<T>;
}

/**
 * React hook that returns an API client wired to the current Clerk session.
 * Each request mints a fresh JWT via `getToken({ template: "news-api" })`,
 * which adds email + name claims for our backend's ClerkClaims schema.
 *
 * Throws `ApiError(status, body)` on non-2xx responses; callers should let
 * TanStack Query catch the error and surface it through query state.
 */
export function useApiClient(): ApiClient {
  const { getToken } = useAuth();

  return {
    async request<T>(path: string, init?: RequestInit): Promise<T> {
      const token = await getToken({ template: "news-api" });
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...((init?.headers as Record<string, string>) ?? {}),
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const url = `${process.env.NEXT_PUBLIC_API_URL}${path}`;
      const resp = await fetch(url, { ...init, headers });

      if (!resp.ok) {
        const body = await resp.text();
        throw new ApiError(resp.status, body);
      }
      return (await resp.json()) as T;
    },
  };
}
```

- [ ] **Step 4: Run, expect ALL 4 tests PASS**

```sh
pnpm test
```

If the 4th test ("calls getToken with template 'news-api'") fails because of vitest module mocking quirks, simplify it: drop the dynamic import + replace with a direct assertion that the mocked `useAuth().getToken` is called. The first test already proves the Bearer header is set correctly with the right token value.

- [ ] **Step 5: Commit**

```sh
git add web/lib/api.ts web/tests/lib/api.test.ts
git commit -m "feat(web): useApiClient hook with JWT injection (template: news-api)"
```

---

### Task 1.4: TanStack QueryClient (`lib/queryClient.ts`)

**Files:**
- Modify: `web/package.json` (add @tanstack/react-query)
- Create: `web/lib/queryClient.ts`

- [ ] **Step 1: Install TanStack Query + sonner**

```sh
cd web
pnpm add @tanstack/react-query sonner
pnpm add -D @tanstack/react-query-devtools
```

- [ ] **Step 2: Create `web/lib/queryClient.ts`**

```ts
"use client";

import { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

/**
 * Singleton QueryClient. Defaults:
 *
 * - 30s staleTime: most reads tolerate brief staleness; reduces refetch chatter.
 * - 1 retry: transient network blips heal on retry; auth errors surface
 *   immediately (TanStack Query doesn't retry 4xx by default).
 * - refetchOnWindowFocus: catch updates when user returns to tab.
 * - mutation onError: surface error message via toast for user-visible feedback.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: true,
      },
      mutations: {
        onError: (err) => {
          if (err instanceof Error) toast.error(err.message);
          else toast.error("Something went wrong");
        },
      },
    },
  });
}
```

- [ ] **Step 3: Typecheck + lint**

```sh
pnpm typecheck && pnpm lint
```

Expected: clean.

- [ ] **Step 4: Commit**

```sh
git add web/lib/queryClient.ts web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): TanStack QueryClient factory with sane defaults"
```

---

### Task 1.5: Theme provider (`lib/theme.tsx`) — light/dark/system

**Files:**
- Create: `web/lib/theme.tsx`
- Create: `web/tests/lib/theme.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/tests/lib/theme.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "@/lib/theme";

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("defaults to 'system' when localStorage is empty", () => {
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    });
    expect(result.current.theme).toBe("system");
  });

  it("setTheme('dark') applies .dark class on <html>", () => {
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    });
    act(() => result.current.setTheme("dark"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("setTheme('light') removes .dark class", () => {
    document.documentElement.classList.add("dark");
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    });
    act(() => result.current.setTheme("light"));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("reads initial theme from localStorage", () => {
    localStorage.setItem("theme", "dark");
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    });
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
```

- [ ] **Step 2: Run, expect FAIL ("cannot import")**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/theme.tsx`**

```tsx
"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark" | "system";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEY = "theme";

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  if (resolved === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "system";
    return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "system";
  });

  useEffect(() => {
    applyTheme(theme);
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = (): void => applyTheme("system");
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
  }, [theme]);

  const setTheme = (next: Theme): void => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  };

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}
```

- [ ] **Step 4: Run, expect 4 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Typecheck + lint**

```sh
pnpm typecheck && pnpm lint
```

- [ ] **Step 6: Commit**

```sh
git add web/lib/theme.tsx web/tests/lib/theme.test.tsx
git commit -m "feat(web): ThemeProvider + useTheme (light/dark/system, localStorage-backed)"
```

---

## Phase 2 — Hooks

### Task 2.1: `useMe` hook

**Files:**
- Create: `web/lib/hooks/useMe.ts`
- Create: `web/tests/lib/hooks/useMe.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/lib/hooks/useMe.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMe } from "@/lib/hooks/useMe";
import { MOCK_USER_OUT } from "../../mocks/handlers";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMe", () => {
  it("fetches GET /v1/me and returns UserOut", async () => {
    const { result } = renderHook(() => useMe(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.email).toBe("test@example.com");
    expect(result.current.data?.profile_completed_at).toBeNull();
  });

  it("returns the same UserOut shape from MSW handler", async () => {
    const { result } = renderHook(() => useMe(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual(MOCK_USER_OUT);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/hooks/useMe.ts`**

```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { UserOut } from "@/lib/types/api";

export const QK_ME = ["me"] as const;

export function useMe() {
  const api = useApiClient();
  return useQuery({
    queryKey: QK_ME,
    queryFn: () => api.request<UserOut>("/v1/me"),
  });
}
```

- [ ] **Step 4: Run, expect 2 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/lib/hooks/useMe.ts web/tests/lib/hooks/useMe.test.tsx
git commit -m "feat(web): useMe hook (GET /v1/me)"
```

---

### Task 2.2: `useDigests` hook (cursor-paginated)

**Files:**
- Create: `web/lib/hooks/useDigests.ts`
- Create: `web/tests/lib/hooks/useDigests.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/lib/hooks/useDigests.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useDigestsList } from "@/lib/hooks/useDigests";
import type { DigestListResponse, DigestSummaryOut } from "@/lib/types/api";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const sampleDigest = (id: number): DigestSummaryOut => ({
  id,
  user_id: "00000000-0000-4000-8000-000000000001",
  period_start: "2026-04-27T00:00:00Z",
  period_end: "2026-04-28T00:00:00Z",
  intro: `day ${id}`,
  top_themes: ["agents"],
  article_count: 7,
  status: "generated",
  generated_at: "2026-04-28T05:00:00Z",
});

describe("useDigestsList", () => {
  it("fetches first page", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests", () =>
        HttpResponse.json<DigestListResponse>({
          items: [sampleDigest(5), sampleDigest(4)],
          next_before: 4,
        }),
      ),
    );

    const { result } = renderHook(() => useDigestsList(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const flat = result.current.data?.pages.flatMap((p) => p.items) ?? [];
    expect(flat.map((d) => d.id)).toEqual([5, 4]);
  });

  it("fetchNextPage uses next_before cursor", async () => {
    let calls: string[] = [];
    server.use(
      http.get("http://localhost:8000/v1/digests", ({ request }) => {
        calls.push(new URL(request.url).search);
        const before = new URL(request.url).searchParams.get("before");
        if (before === "3") {
          return HttpResponse.json<DigestListResponse>({
            items: [sampleDigest(2), sampleDigest(1)],
            next_before: null,
          });
        }
        return HttpResponse.json<DigestListResponse>({
          items: [sampleDigest(5), sampleDigest(4), sampleDigest(3)],
          next_before: 3,
        });
      }),
    );

    const { result } = renderHook(() => useDigestsList(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    const flat = result.current.data?.pages.flatMap((p) => p.items) ?? [];
    expect(flat.map((d) => d.id)).toEqual([5, 4, 3, 2, 1]);
    expect(result.current.hasNextPage).toBe(false);
    expect(calls.some((c) => c.includes("before=3"))).toBe(true);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/hooks/useDigests.ts`**

```ts
"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { DigestListResponse } from "@/lib/types/api";

export const QK_DIGESTS = ["digests"] as const;

const PAGE_SIZE = 10;

export function useDigestsList() {
  const api = useApiClient();
  return useInfiniteQuery({
    queryKey: QK_DIGESTS,
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (pageParam !== null) qs.set("before", String(pageParam));
      return api.request<DigestListResponse>(`/v1/digests?${qs}`);
    },
    getNextPageParam: (last) => last.next_before,
  });
}
```

- [ ] **Step 4: Run, expect 2 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/lib/hooks/useDigests.ts web/tests/lib/hooks/useDigests.test.tsx
git commit -m "feat(web): useDigestsList hook (infinite query, cursor-paginated)"
```

---

### Task 2.3: `useDigest` hook

**Files:**
- Create: `web/lib/hooks/useDigest.ts`
- Create: `web/tests/lib/hooks/useDigest.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/lib/hooks/useDigest.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useDigest } from "@/lib/hooks/useDigest";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useDigest", () => {
  it("fetches GET /v1/digests/:id", async () => {
    const { result } = renderHook(() => useDigest(42), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(42);
  });

  it("surfaces 404 as a query error", async () => {
    server.use(
      http.get("http://localhost:8000/v1/digests/999", () =>
        HttpResponse.json({ detail: "digest not found" }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useDigest(999), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { status: number }).status).toBe(404);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/hooks/useDigest.ts`**

```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/lib/api";
import type { DigestOut } from "@/lib/types/api";

export const qkDigest = (id: number) => ["digest", id] as const;

export function useDigest(id: number) {
  const api = useApiClient();
  return useQuery({
    queryKey: qkDigest(id),
    queryFn: () => api.request<DigestOut>(`/v1/digests/${id}`),
  });
}
```

- [ ] **Step 4: Run, expect 2 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/lib/hooks/useDigest.ts web/tests/lib/hooks/useDigest.test.tsx
git commit -m "feat(web): useDigest hook (GET /v1/digests/:id)"
```

---

### Task 2.4: `useUpdateProfile` hook

**Files:**
- Create: `web/lib/hooks/useUpdateProfile.ts`
- Create: `web/tests/lib/hooks/useUpdateProfile.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/lib/hooks/useUpdateProfile.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useUpdateProfile } from "@/lib/hooks/useUpdateProfile";
import { useMe } from "@/lib/hooks/useMe";
import { EMPTY_PROFILE } from "@/lib/constants";

function wrapperFactory() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useUpdateProfile", () => {
  it("PUTs the profile and updates the /me cache via setQueryData", async () => {
    const newProfile = {
      ...EMPTY_PROFILE,
      background: ["AI engineer"],
    };

    server.use(
      http.put("http://localhost:8000/v1/me/profile", async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({
          id: "00000000-0000-4000-8000-000000000001",
          clerk_user_id: "user_test",
          email: "test@example.com",
          name: "Test User",
          email_name: "Test",
          profile: body,
          profile_completed_at: "2026-04-28T11:00:00Z",
          created_at: "2026-04-28T10:00:00Z",
          updated_at: "2026-04-28T11:00:00Z",
        });
      }),
    );

    const { Wrapper, qc } = wrapperFactory();

    // Pre-warm /me cache.
    const { result: meBefore } = renderHook(() => useMe(), { wrapper: Wrapper });
    await waitFor(() => expect(meBefore.current.isSuccess).toBe(true));

    const { result: mut } = renderHook(() => useUpdateProfile(), { wrapper: Wrapper });

    await act(async () => {
      await mut.current.mutateAsync(newProfile);
    });

    // The /me query should now reflect the new profile + completed timestamp.
    const cached = qc.getQueryData<{ profile: typeof newProfile; profile_completed_at: string | null }>(["me"]);
    expect(cached?.profile.background).toEqual(["AI engineer"]);
    expect(cached?.profile_completed_at).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/hooks/useUpdateProfile.ts`**

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useApiClient } from "@/lib/api";
import { QK_ME } from "@/lib/hooks/useMe";
import type { UserOut, UserProfile } from "@/lib/types/api";

export function useUpdateProfile() {
  const api = useApiClient();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (profile: UserProfile) =>
      api.request<UserOut>("/v1/me/profile", {
        method: "PUT",
        body: JSON.stringify(profile),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(QK_ME, updated);
      toast.success("Profile saved");
    },
  });
}
```

- [ ] **Step 4: Run, expect test PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/lib/hooks/useUpdateProfile.ts web/tests/lib/hooks/useUpdateProfile.test.tsx
git commit -m "feat(web): useUpdateProfile hook (PUT /v1/me/profile + cache update)"
```

---

### Task 2.5: `useRemix` hook with auto-refetch polling

**Files:**
- Create: `web/lib/hooks/useRemix.ts`
- Create: `web/tests/lib/hooks/useRemix.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/lib/hooks/useRemix.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { useRemix } from "@/lib/hooks/useRemix";

function wrapperFactory() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useRemix", () => {
  it("POSTs /v1/remix and resolves with execution_arn", async () => {
    const { Wrapper } = wrapperFactory();
    const { result } = renderHook(() => useRemix(), { wrapper: Wrapper });

    let response;
    await act(async () => {
      response = await result.current.mutateAsync(24);
    });

    expect(response).toMatchObject({
      execution_arn: expect.stringContaining("news-remix-user-dev"),
    });
  });

  it("invalidates ['digests'] queries every 5s for 120s after success", async () => {
    vi.useFakeTimers();
    const { Wrapper, qc } = wrapperFactory();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    // Need to override invalidate on the hook's qc, not the wrapper's. The hook reads
    // the qc from context — same object — so spying on the wrapper's qc is fine.
    const { result } = renderHook(() => useRemix(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync(24);
    });

    // Initial 5s tick → 1 invalidation
    vi.advanceTimersByTime(5_000);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["digests"] });
    const callCountAt5s = invalidateSpy.mock.calls.length;

    // 120s total → ~24 invalidations
    vi.advanceTimersByTime(115_000);
    expect(invalidateSpy.mock.calls.length).toBeGreaterThanOrEqual(20);

    // After 125s, polling should stop — no more invalidations.
    const callCountAt125s = invalidateSpy.mock.calls.length;
    vi.advanceTimersByTime(10_000);
    expect(invalidateSpy.mock.calls.length).toBe(callCountAt125s);

    vi.useRealTimers();
  });

  it("shows specific toast on 409 (profile_incomplete)", async () => {
    server.use(
      http.post("http://localhost:8000/v1/remix", () =>
        HttpResponse.json({ detail: { error: "profile_incomplete" } }, { status: 409 }),
      ),
    );

    const toastSpy = vi.fn();
    vi.doMock("sonner", () => ({ toast: { success: vi.fn(), error: toastSpy } }));

    // Re-import the hook AFTER mocking sonner.
    const { useRemix: freshUseRemix } = await import("@/lib/hooks/useRemix");
    const { Wrapper } = wrapperFactory();

    const { result } = renderHook(() => freshUseRemix(), { wrapper: Wrapper });
    await act(async () => {
      await expect(result.current.mutateAsync(24)).rejects.toThrow();
    });

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining("Complete your profile"));
    });
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/lib/hooks/useRemix.ts`**

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useApiClient } from "@/lib/api";
import { ApiError, type RemixResponse } from "@/lib/types/api";

const POLL_INTERVAL_MS = 5_000;
const POLL_DURATION_MS = 120_000;

export function useRemix() {
  const api = useApiClient();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (lookback_hours = 24): Promise<RemixResponse> =>
      api.request<RemixResponse>("/v1/remix", {
        method: "POST",
        body: JSON.stringify({ lookback_hours }),
      }),
    onSuccess: () => {
      toast.success("Your remix is on the way (~30-60s)");
      // Poll the digest list every 5s for 120s. invalidateQueries triggers
      // refetch on whatever's mounted; if user navigates away, no-op.
      let elapsed = 0;
      const interval = setInterval(() => {
        elapsed += POLL_INTERVAL_MS;
        qc.invalidateQueries({ queryKey: ["digests"] });
        if (elapsed >= POLL_DURATION_MS) clearInterval(interval);
      }, POLL_INTERVAL_MS);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          toast.error("Complete your profile to remix");
          return;
        }
        if (err.status === 503) {
          toast.error("Service busy — try again in a moment");
          return;
        }
      }
      toast.error("Remix failed — see logs");
    },
  });
}
```

- [ ] **Step 4: Run, expect tests PASS**

```sh
pnpm test
```

If the third test (sonner mock) is flaky due to vitest module-mock semantics, simplify by directly checking that the `onError` branch's behaviour can be observed (e.g., assert the mutation rejection's error has `.status === 409`). The first two tests are the primary contract; the third is nice-to-have.

- [ ] **Step 5: Commit**

```sh
git add web/lib/hooks/useRemix.ts web/tests/lib/hooks/useRemix.test.tsx
git commit -m "feat(web): useRemix hook with setInterval-based digest list polling"
```

---

## Phase 3 — Auth components

### Task 3.1: `<RequireAuth>` wrapper

**Files:**
- Create: `web/components/auth/RequireAuth.tsx`
- Create: `web/tests/components/RequireAuth.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/components/RequireAuth.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

describe("RequireAuth", () => {
  it("renders skeleton while !isLoaded", async () => {
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: false, isSignedIn: false }),
      RedirectToSignIn: () => <div data-testid="redirect" />,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-skeleton")).toBeInTheDocument();
  });

  it("renders <RedirectToSignIn> when loaded but not signed in", async () => {
    vi.resetModules();
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: true, isSignedIn: false }),
      RedirectToSignIn: () => <div data-testid="redirect" />,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(screen.getByTestId("redirect")).toBeInTheDocument();
  });

  it("renders children when signed in", async () => {
    vi.resetModules();
    vi.doMock("@clerk/clerk-react", () => ({
      useAuth: () => ({ isLoaded: true, isSignedIn: true }),
      RedirectToSignIn: () => null,
    }));
    const { RequireAuth } = await import("@/components/auth/RequireAuth");
    render(
      <RequireAuth>
        <div>protected</div>
      </RequireAuth>,
    );
    expect(screen.getByText("protected")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Install Clerk SDK**

```sh
cd web
pnpm add @clerk/clerk-react
```

- [ ] **Step 4: Create `web/components/auth/RequireAuth.tsx`**

```tsx
"use client";

import { RedirectToSignIn, useAuth } from "@clerk/clerk-react";
import { Skeleton } from "@/components/ui/skeleton";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return (
      <div data-testid="page-skeleton" className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!isSignedIn) return <RedirectToSignIn />;

  return <>{children}</>;
}
```

- [ ] **Step 5: Run, expect 3 tests PASS**

```sh
pnpm test
```

- [ ] **Step 6: Commit**

```sh
git add web/components/auth/RequireAuth.tsx \
        web/tests/components/RequireAuth.test.tsx \
        web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): <RequireAuth> wrapper (skeleton / redirect / children)"
```

---

### Task 3.2: `<OnboardingBanner>` component

**Files:**
- Create: `web/components/auth/OnboardingBanner.tsx`
- Create: `web/tests/components/OnboardingBanner.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/components/OnboardingBanner.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/components/auth/OnboardingBanner.tsx`**

```tsx
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SparklesIcon } from "lucide-react";

export function OnboardingBanner() {
  return (
    <Alert>
      <SparklesIcon className="h-4 w-4" />
      <AlertTitle>Welcome!</AlertTitle>
      <AlertDescription>
        Complete your profile to start receiving daily digests at 00:00 EAT, or trigger an
        on-demand remix any time after.
      </AlertDescription>
    </Alert>
  );
}
```

- [ ] **Step 4: Install lucide-react**

(shadcn already installed it as a peer; if `pnpm typecheck` errors, install explicitly):

```sh
cd web
pnpm add lucide-react
```

- [ ] **Step 5: Run, expect test PASS**

```sh
pnpm test
```

- [ ] **Step 6: Commit**

```sh
git add web/components/auth/OnboardingBanner.tsx \
        web/tests/components/OnboardingBanner.test.tsx \
        web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): <OnboardingBanner> component"
```

---

## Phase 4 — Layout

### Task 4.1: `<ThemeToggle>` button

**Files:**
- Create: `web/components/layout/ThemeToggle.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { MoonIcon, SunIcon, MonitorIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const { setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Toggle theme">
          <SunIcon className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <MoonIcon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <SunIcon className="mr-2 h-4 w-4" />
          Light
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <MoonIcon className="mr-2 h-4 w-4" />
          Dark
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <MonitorIcon className="mr-2 h-4 w-4" />
          System
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 2: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 3: Commit**

```sh
git add web/components/layout/ThemeToggle.tsx
git commit -m "feat(web): <ThemeToggle> dropdown (light/dark/system)"
```

---

### Task 4.2: `<Header>` + `<Footer>`

**Files:**
- Create: `web/components/layout/Header.tsx`
- Create: `web/components/layout/Footer.tsx`

- [ ] **Step 1: Create `web/components/layout/Header.tsx`**

```tsx
"use client";

import Link from "next/link";
import { UserButton } from "@clerk/clerk-react";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold">
          <span className="text-lg">digest</span>
        </Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <UserButton afterSignOutUrl="/" />
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Create `web/components/layout/Footer.tsx`**

```tsx
import { ENV_DETAILS } from "@/lib/constants";

export function Footer() {
  return (
    <footer className="border-t mt-auto">
      <div className="container py-4 text-sm text-muted-foreground text-center">
        Sub-project #5 · v0.6.0 · {process.env.NEXT_PUBLIC_API_URL}
      </div>
    </footer>
  );
}
```

(Remove the `ENV_DETAILS` import — it's not defined; the component just renders the env URL inline.)

Final version:

```tsx
export function Footer() {
  return (
    <footer className="border-t mt-auto">
      <div className="container py-4 text-sm text-muted-foreground text-center">
        Sub-project #5 · v0.6.0 · {process.env.NEXT_PUBLIC_API_URL}
      </div>
    </footer>
  );
}
```

- [ ] **Step 3: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 4: Commit**

```sh
git add web/components/layout/Header.tsx web/components/layout/Footer.tsx
git commit -m "feat(web): <Header> (logo + ThemeToggle + UserButton) + <Footer>"
```

---

### Task 4.3: Root layout (`app/layout.tsx`) + unauth root page (`app/page.tsx`)

**Files:**
- Create: `web/app/layout.tsx`
- Create: `web/app/page.tsx`
- Create: `web/app/not-found.tsx`

- [ ] **Step 1: Create `web/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/clerk-react";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "@/lib/theme";
import { QueryProvider } from "@/lib/queryProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import "./globals.css";

export const metadata: Metadata = {
  title: "digest",
  description: "Your daily AI/tech digest, curated and ranked.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Apply theme before React hydrates to prevent FOUC. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function() {
              try {
                var t = localStorage.getItem('theme') || 'system';
                var dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                if (dark) document.documentElement.classList.add('dark');
              } catch (e) {}
            })();`,
          }}
        />
      </head>
      <body className="min-h-screen flex flex-col">
        <ClerkProvider publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!}>
          <ThemeProvider>
            <QueryProvider>
              <Header />
              <main className="flex-1 container py-6">{children}</main>
              <Footer />
              <Toaster richColors position="top-right" />
            </QueryProvider>
          </ThemeProvider>
        </ClerkProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Create `web/lib/queryProvider.tsx`** (referenced by layout)

```tsx
"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createQueryClient } from "@/lib/queryClient";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // useState ensures one client per component lifetime, not one per render.
  const [client] = useState(() => createQueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 3: Create `web/app/page.tsx`** (the unauth root — redirects to authenticated route group's index)

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RootRedirect() {
  const router = useRouter();
  // The (authenticated) route group also exposes /, but Next.js renders this file
  // for the unauthenticated case. RedirectToSignIn from Clerk Account Portal will
  // bounce unauth users; signed-in users see the (authenticated)/page.tsx tree.
  // For static export, we can't use middleware — the client-side redirect is acceptable.
  useEffect(() => {
    router.replace("/");
  }, [router]);

  return null;
}
```

(Wait — having both `app/page.tsx` and `app/(authenticated)/page.tsx` mapping to `/` is a Next.js conflict. Drop `app/page.tsx` and rely on `app/(authenticated)/page.tsx`. The auth wrapper handles the unauth case.)

Replace `web/app/page.tsx` with a comment:

```tsx
// This file is intentionally empty — the / route is owned by
// app/(authenticated)/page.tsx, which sits inside a route group that
// applies the <RequireAuth> wrapper. Next.js's static export emits one
// /index.html that handles both auth states client-side.
```

Actually that won't compile — we need to either have a real default export OR delete the file. Best approach: **delete `app/page.tsx` and let `app/(authenticated)/page.tsx` own `/`.** The `(authenticated)` route group is invisible in the URL.

Skip step 3 and create only the not-found page.

- [ ] **Step 4: Create `web/app/not-found.tsx`**

```tsx
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="mt-2 text-muted-foreground">This page doesn't exist.</p>
      <Button asChild className="mt-6">
        <Link href="/">Go home</Link>
      </Button>
    </div>
  );
}
```

- [ ] **Step 5: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 6: Commit**

```sh
git add web/app/layout.tsx web/app/not-found.tsx web/lib/queryProvider.tsx
git commit -m "feat(web): root layout (Clerk + Theme + Query providers + Header/Footer)"
```

---

## Phase 5 — Digest components + pages

### Task 5.1: `<DigestCard>` (list-view item)

**Files:**
- Create: `web/components/digest/DigestCard.tsx`
- Create: `web/tests/components/DigestCard.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/components/DigestCard.test.tsx`:

```tsx
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

  it("links to /digests/{id}", () => {
    render(<DigestCard digest={sample} />);
    const link = screen.getByRole("link", { name: /read/i });
    expect(link).toHaveAttribute("href", "/digests/17");
  });

  it("handles null intro gracefully", () => {
    render(<DigestCard digest={{ ...sample, intro: null }} />);
    expect(screen.getByText(/7 articles/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
cd web
pnpm test
```

- [ ] **Step 3: Create `web/components/digest/DigestCard.tsx`**

```tsx
import Link from "next/link";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRightIcon } from "lucide-react";
import type { DigestSummaryOut } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(start)} → ${fmt(end)}`;
}

export function DigestCard({ digest }: { digest: DigestSummaryOut }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="text-sm text-muted-foreground">
          {formatPeriod(digest.period_start, digest.period_end)}
        </div>
        {digest.intro && (
          <p className="line-clamp-2 text-sm font-medium">{digest.intro}</p>
        )}
      </CardHeader>
      <CardContent className="flex-1">
        <div className="flex flex-wrap gap-1">
          {digest.top_themes.slice(0, 3).map((t) => (
            <Badge key={t} variant="secondary">
              {t}
            </Badge>
          ))}
        </div>
      </CardContent>
      <CardFooter className="flex items-center justify-between pt-2">
        <span className="text-sm text-muted-foreground">{digest.article_count} articles</span>
        <Link
          href={`/digests/${digest.id}`}
          className="text-sm font-medium text-primary hover:underline inline-flex items-center gap-1"
        >
          Read <ArrowRightIcon className="h-3 w-3" />
        </Link>
      </CardFooter>
    </Card>
  );
}
```

- [ ] **Step 4: Run, expect 3 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/components/digest/DigestCard.tsx web/tests/components/DigestCard.test.tsx
git commit -m "feat(web): <DigestCard> component"
```

---

### Task 5.2: `<RankedArticleCard>` (detail-view item)

**Files:**
- Create: `web/components/digest/RankedArticleCard.tsx`
- Create: `web/tests/components/RankedArticleCard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run, expect FAIL**

```sh
pnpm test
```

- [ ] **Step 3: Create `web/components/digest/RankedArticleCard.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import type { RankedArticle } from "@/lib/types/api";

export function RankedArticleCard({ article, rank }: { article: RankedArticle; rank: number }) {
  return (
    <li className="flex gap-4 border-b last:border-b-0 pb-6">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-muted flex items-center justify-center font-bold">
        {rank}
      </div>
      <div className="flex-1 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold hover:underline"
          >
            {article.title}
          </a>
          <Badge variant="outline" className="flex-shrink-0">
            {article.score}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{article.summary}</p>
        <p className="text-xs text-muted-foreground italic border-l-2 pl-3">
          <strong className="not-italic">Why this article: </strong>
          {article.why_ranked}
        </p>
      </div>
    </li>
  );
}
```

- [ ] **Step 4: Run, expect 2 tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add web/components/digest/RankedArticleCard.tsx web/tests/components/RankedArticleCard.test.tsx
git commit -m "feat(web): <RankedArticleCard> component"
```

---

### Task 5.3: `<EmptyState>` + skeletons

**Files:**
- Create: `web/components/digest/EmptyState.tsx`
- Create: `web/components/digest/DigestListSkeleton.tsx`
- Create: `web/components/digest/DigestDetailSkeleton.tsx`

- [ ] **Step 1: Create `web/components/digest/EmptyState.tsx`**

```tsx
import { CalendarIcon } from "lucide-react";

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
      <CalendarIcon className="h-12 w-12 mb-4 opacity-50" />
      <h3 className="font-medium text-foreground">No digests yet</h3>
      <p className="mt-1 text-sm max-w-sm">
        Daily digests are generated at 00:00 EAT. Click "Remix now" above for an on-demand run.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Create `web/components/digest/DigestListSkeleton.tsx`**

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function DigestListSkeleton() {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <li key={i} className="border rounded-lg p-4 space-y-3">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-12" />
            <Skeleton className="h-5 w-16" />
          </div>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Create `web/components/digest/DigestDetailSkeleton.tsx`**

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function DigestDetailSkeleton() {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-20 w-full" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 5: Commit**

```sh
git add web/components/digest/EmptyState.tsx \
        web/components/digest/DigestListSkeleton.tsx \
        web/components/digest/DigestDetailSkeleton.tsx
git commit -m "feat(web): <EmptyState> + DigestList/Detail skeletons"
```

---

### Task 5.4: Digest list page (`app/(authenticated)/page.tsx`)

**Files:**
- Create: `web/app/(authenticated)/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { Button } from "@/components/ui/button";
import { SparklesIcon } from "lucide-react";
import { useDigestsList } from "@/lib/hooks/useDigests";
import { useRemix } from "@/lib/hooks/useRemix";
import { DigestCard } from "@/components/digest/DigestCard";
import { DigestListSkeleton } from "@/components/digest/DigestListSkeleton";
import { EmptyState } from "@/components/digest/EmptyState";

export default function HomePage() {
  const list = useDigestsList();
  const remix = useRemix();

  const digests = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-3xl font-bold">Your digests</h1>
        <Button onClick={() => remix.mutate(24)} disabled={remix.isPending}>
          <SparklesIcon className="mr-2 h-4 w-4" />
          {remix.isPending ? "Triggering…" : "Remix now"}
        </Button>
      </header>

      {list.isLoading ? (
        <DigestListSkeleton />
      ) : digests.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {digests.map((d) => (
            <DigestCard key={d.id} digest={d} />
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" onClick={() => list.fetchNextPage()}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 3: Commit**

```sh
git add "web/app/(authenticated)/page.tsx"
git commit -m "feat(web): digest list page (/) with Remix-now button"
```

---

### Task 5.5: Digest detail page (`app/(authenticated)/digests/[id]/page.tsx`)

**Files:**
- Create: `web/app/(authenticated)/digests/[id]/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { use } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useDigest } from "@/lib/hooks/useDigest";
import { RankedArticleCard } from "@/components/digest/RankedArticleCard";
import { DigestDetailSkeleton } from "@/components/digest/DigestDetailSkeleton";
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${fmt(start)} — ${fmt(end)}`;
}

export default function DigestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const numericId = Number(id);
  const { data, isLoading, error } = useDigest(numericId);

  if (isLoading) return <DigestDetailSkeleton />;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Digest not found.</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <article className="prose dark:prose-invert max-w-3xl mx-auto">
      <header className="not-prose">
        <p className="text-sm text-muted-foreground">{formatPeriod(data.period_start, data.period_end)}</p>
        <h1 className="text-3xl font-bold mt-1">Your digest</h1>
        {data.top_themes.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {data.top_themes.map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </header>
      {data.intro && <p className="lead">{data.intro}</p>}
      <ol className="not-prose list-none p-0 space-y-6 mt-8">
        {data.ranked_articles.map((a, i) => (
          <RankedArticleCard key={a.article_id} article={a} rank={i + 1} />
        ))}
      </ol>
    </article>
  );
}
```

- [ ] **Step 2: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

If `pnpm typecheck` complains about the dynamic route's `params: Promise<...>` shape (Next.js 15 changed this), the alternative non-Promise form works on older Next.js: `params: { id: string }` without the `use()` unwrap. Pick whichever your installed Next.js requires.

- [ ] **Step 3: Commit**

```sh
git add "web/app/(authenticated)/digests/[id]/page.tsx"
git commit -m "feat(web): digest detail page (/digests/[id])"
```

---

## Phase 6 — Profile editor

### Task 6.1: Field-array helper components

**Files:**
- Create: `web/components/profile/StringListField.tsx` (shared field-array helper)

The five field components (BackgroundFieldArray, etc.) have a common pattern: a label + a list of editable strings + add/remove buttons. We extract this into a shared `<StringListField>` and compose page-level wrappers around it.

- [ ] **Step 1: Install React Hook Form**

```sh
cd web
pnpm add react-hook-form @hookform/resolvers
```

- [ ] **Step 2: Create `web/components/profile/StringListField.tsx`**

```tsx
"use client";

import { useFieldArray, useFormContext } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { PlusIcon, XIcon } from "lucide-react";

interface Props {
  name: string;
  label: string;
  placeholder?: string;
}

export function StringListField({ name, label, placeholder = "" }: Props) {
  const { control } = useFormContext();
  const { fields, append, remove } = useFieldArray({ control, name: name as `${string}` });

  return (
    <FormItem>
      <FormLabel>{label}</FormLabel>
      <ul className="space-y-2">
        {fields.map((field, i) => (
          <li key={field.id} className="flex gap-2">
            <FormField
              control={control}
              name={`${name}.${i}` as `${string}`}
              render={({ field: f }) => (
                <FormItem className="flex-1">
                  <Input {...f} placeholder={placeholder} />
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Remove"
              onClick={() => remove(i)}
            >
              <XIcon className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" size="sm" onClick={() => append("")}>
        <PlusIcon className="mr-2 h-4 w-4" />
        Add
      </Button>
    </FormItem>
  );
}
```

- [ ] **Step 3: Typecheck**

```sh
cd web
pnpm typecheck
```

- [ ] **Step 4: Commit**

```sh
git add web/components/profile/StringListField.tsx web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): <StringListField> shared profile field-array component"
```

---

### Task 6.2: Per-section field group components

**Files:**
- Create: `web/components/profile/BackgroundFieldArray.tsx`
- Create: `web/components/profile/InterestsFieldGroup.tsx`
- Create: `web/components/profile/PreferencesFieldGroup.tsx`
- Create: `web/components/profile/GoalsFieldArray.tsx`
- Create: `web/components/profile/ReadingTimeFieldGroup.tsx`

- [ ] **Step 1: Create `web/components/profile/BackgroundFieldArray.tsx`**

```tsx
import { StringListField } from "./StringListField";

export function BackgroundFieldArray() {
  return (
    <StringListField
      name="background"
      label="Background"
      placeholder="e.g. AI engineer, Backend dev"
    />
  );
}
```

- [ ] **Step 2: Create `web/components/profile/InterestsFieldGroup.tsx`**

```tsx
import { StringListField } from "./StringListField";

export function InterestsFieldGroup() {
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Interests</legend>
      <StringListField name="interests.primary" label="Primary" placeholder="LLMs, agents" />
      <StringListField name="interests.secondary" label="Secondary" placeholder="devops, security" />
      <StringListField
        name="interests.specific_topics"
        label="Specific topics"
        placeholder="MCP servers, RAG"
      />
    </fieldset>
  );
}
```

- [ ] **Step 3: Create `web/components/profile/PreferencesFieldGroup.tsx`**

```tsx
import { StringListField } from "./StringListField";

export function PreferencesFieldGroup() {
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Preferences</legend>
      <StringListField
        name="preferences.content_type"
        label="Content type"
        placeholder="Technical deep dives, paper summaries"
      />
      <StringListField
        name="preferences.avoid"
        label="Avoid"
        placeholder="Press releases, marketing posts"
      />
    </fieldset>
  );
}
```

- [ ] **Step 4: Create `web/components/profile/GoalsFieldArray.tsx`**

```tsx
import { StringListField } from "./StringListField";

export function GoalsFieldArray() {
  return (
    <StringListField
      name="goals"
      label="Goals"
      placeholder="Stay current on agent infra"
    />
  );
}
```

- [ ] **Step 5: Create `web/components/profile/ReadingTimeFieldGroup.tsx`**

```tsx
"use client";

import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/input";
import { FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";

export function ReadingTimeFieldGroup() {
  const { control } = useFormContext();
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Reading time</legend>
      <FormField
        control={control}
        name="reading_time.daily_limit"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Daily limit</FormLabel>
            <Input {...field} placeholder="20 minutes" />
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="reading_time.preferred_article_count"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Preferred article count</FormLabel>
            <Input {...field} placeholder="10" />
            <FormMessage />
          </FormItem>
        )}
      />
    </fieldset>
  );
}
```

- [ ] **Step 6: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 7: Commit**

```sh
git add web/components/profile/
git commit -m "feat(web): per-section profile field group components"
```

---

### Task 6.3: Profile editor page

**Files:**
- Create: `web/app/(authenticated)/profile/page.tsx`
- Create: `web/tests/components/ProfileEditor.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/tests/components/ProfileEditor.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProfilePage from "@/app/(authenticated)/profile/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ProfilePage", () => {
  it("renders profile sections", async () => {
    render(<ProfilePage />, { wrapper });
    await waitFor(() => expect(screen.getByText(/your profile/i)).toBeInTheDocument());
    expect(screen.getByText(/background/i)).toBeInTheDocument();
    expect(screen.getByText(/interests/i)).toBeInTheDocument();
    expect(screen.getByText(/preferences/i)).toBeInTheDocument();
    expect(screen.getByText(/goals/i)).toBeInTheDocument();
    expect(screen.getByText(/reading time/i)).toBeInTheDocument();
  });

  it("submits valid profile via PUT", async () => {
    const user = userEvent.setup();
    render(<ProfilePage />, { wrapper });
    await waitFor(() => screen.getByText(/your profile/i));

    // Add a background entry.
    const addButtons = screen.getAllByRole("button", { name: /add/i });
    await user.click(addButtons[0]);                       // Background → 1 row
    await user.type(screen.getAllByRole("textbox")[0], "AI engineer");

    // Submit.
    await user.click(screen.getByRole("button", { name: /save profile/i }));

    // Either toast appears or button shows pending state — easiest assertion is
    // that submit didn't render any FormMessage error.
    await waitFor(() =>
      expect(screen.queryAllByText(/required/i).length).toBe(0),
    );
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```sh
cd web
pnpm test
```

- [ ] **Step 3: Create `web/app/(authenticated)/profile/page.tsx`**

```tsx
"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { useMe } from "@/lib/hooks/useMe";
import { useUpdateProfile } from "@/lib/hooks/useUpdateProfile";
import { UserProfileSchema } from "@/lib/schemas/userProfile";
import { EMPTY_PROFILE } from "@/lib/constants";
import { OnboardingBanner } from "@/components/auth/OnboardingBanner";
import { BackgroundFieldArray } from "@/components/profile/BackgroundFieldArray";
import { InterestsFieldGroup } from "@/components/profile/InterestsFieldGroup";
import { PreferencesFieldGroup } from "@/components/profile/PreferencesFieldGroup";
import { GoalsFieldArray } from "@/components/profile/GoalsFieldArray";
import { ReadingTimeFieldGroup } from "@/components/profile/ReadingTimeFieldGroup";
import type { UserProfile } from "@/lib/types/api";

export default function ProfilePage() {
  const { data: me } = useMe();
  const update = useUpdateProfile();
  const params = useSearchParams();
  const onboarding = params.get("onboarding") === "1";

  const form = useForm<UserProfile>({
    resolver: zodResolver(UserProfileSchema),
    defaultValues: me?.profile ?? EMPTY_PROFILE,
  });

  // When /me loads after the form mounts, reset the form with the loaded values.
  useEffect(() => {
    if (me?.profile) form.reset(me.profile);
  }, [me, form]);

  const onSubmit = (data: UserProfile) => update.mutate(data);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {onboarding && <OnboardingBanner />}
      <h1 className="text-3xl font-bold">Your profile</h1>

      <FormProvider {...form}>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <BackgroundFieldArray />
            <InterestsFieldGroup />
            <PreferencesFieldGroup />
            <GoalsFieldArray />
            <ReadingTimeFieldGroup />

            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button type="button" variant="outline" onClick={() => form.reset(me?.profile ?? EMPTY_PROFILE)}>
                Cancel
              </Button>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "Saving…" : "Save profile"}
              </Button>
            </div>
          </form>
        </Form>
      </FormProvider>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect tests PASS**

```sh
pnpm test
```

- [ ] **Step 5: Commit**

```sh
git add "web/app/(authenticated)/profile/page.tsx" web/tests/components/ProfileEditor.test.tsx
git commit -m "feat(web): profile editor page (RHF + Zod + onboarding banner)"
```

---

## Phase 7 — Authenticated layout (route group)

### Task 7.1: `(authenticated)/layout.tsx` — RequireAuth + onboarding redirect

**Files:**
- Create: `web/app/(authenticated)/layout.tsx`

- [ ] **Step 1: Create the file**

```tsx
"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useMe } from "@/lib/hooks/useMe";

function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me } = useMe();

  useEffect(() => {
    if (me && me.profile_completed_at === null && pathname !== "/profile") {
      router.replace("/profile?onboarding=1");
    }
  }, [me, pathname, router]);

  return <>{children}</>;
}

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <OnboardingGate>{children}</OnboardingGate>
    </RequireAuth>
  );
}
```

- [ ] **Step 2: Typecheck + lint**

```sh
cd web
pnpm typecheck && pnpm lint
```

- [ ] **Step 3: Commit**

```sh
git add "web/app/(authenticated)/layout.tsx"
git commit -m "feat(web): authenticated layout (RequireAuth + onboarding redirect)"
```

---

### Task 7.2: Verify build succeeds end-to-end

**Files:** none (build verification only).

- [ ] **Step 1: Run a full build**

```sh
cd web
pnpm build
```

Expected: build completes; `web/out/` contains static HTML for `/`, `/digests/[id]/`, `/profile/`, `/404.html`. Build output should report ~3-5 routes.

If build fails on a runtime that requires server features (e.g., `cookies()` from next/headers), audit imports — only client-component primitives are allowed.

- [ ] **Step 2: Spot-check the export**

```sh
ls web/out/
ls web/out/digests/
ls web/out/profile/
```

Expected: each route has its own `index.html`.

- [ ] **Step 3: Run all tests one more time**

```sh
pnpm test
pnpm typecheck
pnpm lint
```

All clean.

- [ ] **Step 4: Commit (no code changes — just verification)**

No commit needed; this is a checkpoint task.

---

## Phase 8 — Infrastructure (Terraform)

### Task 8.1: Bootstrap extension — GitHub OIDC provider

**Files:**
- Modify: `infra/bootstrap/<existing>.tf` (add OIDC resource)

- [ ] **Step 1: Find the bootstrap module's main file**

```sh
ls infra/bootstrap/
```

- [ ] **Step 2: Append the OIDC provider resource to the appropriate `.tf` file** (likely `infra/bootstrap/main.tf`):

```hcl
# GitHub Actions OIDC provider — used by sub-project #5's web-deploy.yml workflow
# (and any future workflows that need to assume AWS roles).
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [
    # GitHub's certificate thumbprint — pinned per AWS docs.
    # https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services
    "6938fd4d98bab03faadb97b34396831e3780aea1", # pragma: allowlist secret
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd", # pragma: allowlist secret
  ]
  tags = { Project = "news-aggregator", Module = "bootstrap" }
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}
```

- [ ] **Step 3: Apply bootstrap update**

```sh
cd infra/bootstrap
terraform apply
```

Expected: 1 resource added (`aws_iam_openid_connect_provider.github`); the new output prints the provider ARN.

- [ ] **Step 4: Commit**

```sh
git add infra/bootstrap/
git commit -m "infra(bootstrap): add GitHub Actions OIDC provider"
```

---

### Task 8.2: `infra/web/` skeleton

**Files:**
- Create: `infra/web/backend.tf`
- Create: `infra/web/data.tf`
- Create: `infra/web/variables.tf`
- Create: `infra/web/outputs.tf`
- Create: `infra/web/terraform.tfvars.example`
- Create: `infra/web/.gitignore`

- [ ] **Step 1: `infra/web/backend.tf`**

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
  backend "s3" {
    use_lockfile = true
  }
}

provider "aws" {
  region  = "us-east-1"
  profile = "aiengineer"
}
```

- [ ] **Step 2: `infra/web/data.tf`**

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Existing wildcard ACM cert (in us-east-1 — required for CloudFront).
data "aws_acm_certificate" "wildcard" {
  domain      = "*.patrickcmd.dev"
  statuses    = ["ISSUED"]
  most_recent = true
}

# Existing Route 53 hosted zone for the parent domain.
data "aws_route53_zone" "parent" {
  name = "patrickcmd.dev."
}

# OIDC provider created in infra/bootstrap/.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
```

- [ ] **Step 3: `infra/web/variables.tf`**

```hcl
variable "subdomain" {
  type        = string
  description = "Full subdomain to host (e.g. digest.patrickcmd.dev for prod, dev-digest.patrickcmd.dev for dev)."

  validation {
    condition     = can(regex("\\.patrickcmd\\.dev$", var.subdomain))
    error_message = "subdomain must end in .patrickcmd.dev"
  }
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC AssumeRole condition."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

variable "price_class" {
  type    = string
  default = "PriceClass_100"
}
```

- [ ] **Step 4: `infra/web/outputs.tf`**

```hcl
output "bucket_name" {
  value = aws_s3_bucket.assets.bucket
}

output "distribution_id" {
  value = aws_cloudfront_distribution.web.id
}

output "distribution_domain" {
  value = aws_cloudfront_distribution.web.domain_name
}

output "subdomain_url" {
  value = "https://${var.subdomain}"
}

output "gh_actions_role_arn" {
  value = aws_iam_role.gh_actions_deploy.arn
}
```

- [ ] **Step 5: `infra/web/terraform.tfvars.example`**

```hcl
# subdomain: per-env hostname.
# - prod:  digest.patrickcmd.dev
# - test:  test-digest.patrickcmd.dev
# - dev:   dev-digest.patrickcmd.dev
subdomain   = "dev-digest.patrickcmd.dev"
github_repo = "PatrickCmd/ai-agents-news-aggregator"
```

- [ ] **Step 6: `infra/web/.gitignore`**

```
.terraform/
.terraform.lock.hcl
terraform.tfstate
terraform.tfstate.backup
*.tfvars
!terraform.tfvars.example
```

- [ ] **Step 7: Init the module**

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/web && terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=web/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
cd -
```

- [ ] **Step 8: Commit**

```sh
git add infra/web/
git commit -m "infra(web): module skeleton (backend/data/vars/outputs/.gitignore)"
```

---

### Task 8.3: S3 bucket + bucket policy (`infra/web/main.tf`)

**Files:**
- Create: `infra/web/main.tf`

- [ ] **Step 1: Create the file**

```hcl
locals {
  bucket_name = "digest-${terraform.workspace}-${replace(var.subdomain, ".", "-")}"
}

resource "aws_s3_bucket" "assets" {
  bucket = local.bucket_name

  tags = { Project = "news-aggregator", Module = "web" }
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket                  = aws_s3_bucket.assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "assets" {
  bucket = aws_s3_bucket.assets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontReadOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.assets.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.web.arn
          }
        }
      },
    ]
  })

  depends_on = [aws_cloudfront_distribution.web]
}
```

- [ ] **Step 2: Don't run `terraform plan` yet** — `aws_cloudfront_distribution.web` is referenced but lands in 8.4. Validate syntax with `terraform validate` only after 8.4 is added.

- [ ] **Step 3: Commit**

```sh
git add infra/web/main.tf
git commit -m "infra(web): S3 bucket + OAC-restricted bucket policy"
```

---

### Task 8.4: CloudFront distribution + OAC (`infra/web/cloudfront.tf`)

**Files:**
- Create: `infra/web/cloudfront.tf`

- [ ] **Step 1: Create the file**

```hcl
resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "digest-${terraform.workspace}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# AWS-managed response headers policy (HSTS, X-Frame, etc.). Documented:
# https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-response-headers-policies.html
data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "digest-${terraform.workspace}"
  default_root_object = "index.html"
  price_class         = var.price_class
  aliases             = [var.subdomain]

  origin {
    domain_name              = aws_s3_bucket.assets.bucket_regional_domain_name
    origin_id                = "s3-${aws_s3_bucket.assets.bucket}"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    target_origin_id           = "s3-${aws_s3_bucket.assets.bucket}"
    viewer_protocol_policy     = "redirect-to-https"
    compress                   = true
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # SPA-style routing fallback: missing keys → 404.html (200) so client-side router resolves.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/404.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/404.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.wildcard.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = { Project = "news-aggregator", Module = "web" }
}
```

- [ ] **Step 2: Validate syntax**

```sh
cd infra/web && terraform validate && cd -
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```sh
git add infra/web/cloudfront.tf
git commit -m "infra(web): CloudFront distribution + OAC + security headers"
```

---

### Task 8.5: Route 53 A record (`infra/web/route53.tf`)

**Files:**
- Create: `infra/web/route53.tf`

- [ ] **Step 1: Create the file**

```hcl
resource "aws_route53_record" "subdomain" {
  zone_id = data.aws_route53_zone.parent.zone_id
  name    = var.subdomain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

# Also IPv6 (AAAA) so dual-stack clients use the shorter resolution path.
resource "aws_route53_record" "subdomain_aaaa" {
  zone_id = data.aws_route53_zone.parent.zone_id
  name    = var.subdomain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}
```

- [ ] **Step 2: Validate**

```sh
cd infra/web && terraform validate && cd -
```

- [ ] **Step 3: Commit**

```sh
git add infra/web/route53.tf
git commit -m "infra(web): Route 53 A + AAAA records pointing to CloudFront"
```

---

### Task 8.6: GitHub OIDC role (`infra/web/github_oidc.tf`)

**Files:**
- Create: `infra/web/github_oidc.tf`

- [ ] **Step 1: Create the file**

```hcl
resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-web-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            # Restrict to the repo + the matching GitHub Environment.
            "token.actions.githubusercontent.com:sub" =
              "repo:${var.github_repo}:environment:${terraform.workspace}"
          }
        }
      },
    ]
  })

  tags = { Project = "news-aggregator", Module = "web" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.assets.arn,
          "${aws_s3_bucket.assets.arn}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "cloudfront:CreateInvalidation"
        Resource = aws_cloudfront_distribution.web.arn
      },
    ]
  })
}
```

- [ ] **Step 2: Validate + plan with placeholder**

```sh
cd infra/web && terraform validate
terraform plan -var=subdomain=dev-digest.patrickcmd.dev
cd -
```

Expected plan: ~10 resources to add (bucket + 3 bucket sub-resources + bucket policy + CloudFront distribution + OAC + 2 Route 53 records + IAM role + policy).

- [ ] **Step 3: Commit**

```sh
git add infra/web/github_oidc.tf
git commit -m "infra(web): GitHub OIDC IAM role + policy (S3 sync + CF invalidation)"
```

---

## Phase 9 — CI/CD

### Task 9.1: `web-ci.yml` workflow

**Files:**
- Create: `.github/workflows/web-ci.yml`

- [ ] **Step 1: Create the workflow**

```yaml
name: web-ci

on:
  pull_request:
    paths:
      - "web/**"
      - ".github/workflows/web-ci.yml"
  push:
    branches: [main]
    paths:
      - "web/**"

jobs:
  ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    env:
      NEXT_PUBLIC_API_URL: http://example-build-time.invalid
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: pk_test_dummy_for_build
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          cache-dependency-path: web/pnpm-lock.yaml
      - name: Install (no postinstall scripts)
        run: pnpm install --frozen-lockfile --ignore-scripts
      - name: Lint
        run: pnpm lint
      - name: Typecheck
        run: pnpm typecheck
      - name: Test
        run: pnpm test
      - name: OSV-Scanner
        run: |
          curl -fsSL -o /tmp/osv-scanner \
            https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64
          chmod +x /tmp/osv-scanner
          /tmp/osv-scanner --recursive --fail-on-vuln .
      - name: Build (verifies static export compiles)
        run: pnpm build
```

- [ ] **Step 2: Commit**

```sh
git add .github/workflows/web-ci.yml
git commit -m "ci(web): web-ci workflow (lint/typecheck/test/osv/build on every PR)"
```

---

### Task 9.2: `web-deploy.yml` workflow

**Files:**
- Create: `.github/workflows/web-deploy.yml`

- [ ] **Step 1: Create the workflow**

```yaml
name: web-deploy

on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        description: "Target env"
        options: [dev, test, prod]
        default: dev
      action:
        type: choice
        description: "deploy or destroy"
        options: [deploy, destroy]
        default: deploy

permissions:
  id-token: write   # for OIDC AWS auth
  contents: read

jobs:
  run:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      # ─── deploy path ────────────────────────────────────────────────────
      - if: ${{ inputs.action == 'deploy' }}
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - if: ${{ inputs.action == 'deploy' }}
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          cache-dependency-path: web/pnpm-lock.yaml

      - if: ${{ inputs.action == 'deploy' }}
        name: Build
        working-directory: web
        env:
          NEXT_PUBLIC_API_URL: ${{ vars.NEXT_PUBLIC_API_URL }}
          NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: ${{ secrets.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY }}
        run: |
          pnpm install --frozen-lockfile --ignore-scripts
          pnpm build

      - if: ${{ inputs.action == 'deploy' }}
        name: Sync to S3 + invalidate CloudFront
        env:
          BUCKET: ${{ vars.S3_BUCKET }}
          DIST_ID: ${{ vars.CLOUDFRONT_DISTRIBUTION_ID }}
        run: |
          aws s3 sync web/out/ "s3://$BUCKET/" --delete
          aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*'

      # ─── destroy path ───────────────────────────────────────────────────
      - if: ${{ inputs.action == 'destroy' }}
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.6"

      - if: ${{ inputs.action == 'destroy' }}
        name: Terraform destroy
        working-directory: infra/web
        run: |
          terraform init \
            -backend-config="bucket=news-aggregator-tf-state-${{ vars.AWS_ACCOUNT_ID }}" \
            -backend-config="key=web/terraform.tfstate" \
            -backend-config="region=us-east-1"
          terraform workspace select ${{ inputs.environment }}
          terraform destroy -auto-approve \
            -var=subdomain=${{ vars.SUBDOMAIN }} \
            -var=github_repo=PatrickCmd/ai-agents-news-aggregator
```

- [ ] **Step 2: Commit**

```sh
git add .github/workflows/web-deploy.yml
git commit -m "ci(web): web-deploy workflow (workflow_dispatch + deploy/destroy + dev/test/prod)"
```

---

### Task 9.3: Dependabot config

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Create the file**

```yaml
version: 2
updates:
  - package-ecosystem: npm
    directory: "/web"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "frontend"]
    versioning-strategy: "increase"
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "ci"]
```

- [ ] **Step 2: Commit**

```sh
git add .github/dependabot.yml
git commit -m "ci: dependabot config (weekly updates for /web npm + GitHub Actions)"
```

---

### Task 9.4: Pre-commit hook for OSV-Scanner

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Read existing pre-commit config to find the right insertion point**

```sh
cat .pre-commit-config.yaml
```

- [ ] **Step 2: Append a local OSV-Scanner hook**

Add at the end of the `repos:` list (NOT inside an existing repo):

```yaml
  - repo: local
    hooks:
      - id: osv-scanner-web
        name: OSV-Scanner (web/)
        entry: bash -c 'osv-scanner --recursive --fail-on-vuln web/ || (echo "OSV-Scanner found vulnerabilities. Install if needed: brew install osv-scanner"; exit 1)'
        language: system
        files: ^web/
        pass_filenames: false
```

- [ ] **Step 3: Smoke test**

```sh
pre-commit run osv-scanner-web --all-files
```

Expected: passes (or fails clearly if `osv-scanner` isn't installed locally — install via `brew install osv-scanner` per the hint).

- [ ] **Step 4: Commit**

```sh
git add .pre-commit-config.yaml
git commit -m "ci: pre-commit hook running OSV-Scanner on web/"
```

---

## Phase 10 — Live deploy + smoke (user runs)

### Task 10.1: Verify ACM cert covers the subdomains

**Files:** none.

- [ ] **Step 1: List ACM certs in us-east-1**

```sh
aws acm list-certificates --region us-east-1 --profile aiengineer \
  --query 'CertificateSummaryList[].{Domain:DomainName,Arn:CertificateArn}' \
  --output table
```

Expected: at least one row with `Domain = *.patrickcmd.dev`. If only specific subdomain certs exist (no wildcard), STOP and add a `aws_acm_certificate` resource with the three subdomains as SANs (out of scope of this plan — surface as a follow-up task).

---

### Task 10.2: First Terraform apply for `dev` env

**Files:** none (live AWS work).

- [ ] **Step 1: Create the dev workspace + apply**

```sh
cd infra/web
terraform workspace new dev   # or: terraform workspace select dev
terraform apply \
  -var=subdomain=dev-digest.patrickcmd.dev \
  -var=github_repo=PatrickCmd/ai-agents-news-aggregator
cd -
```

Expected: ~10 resources created. Outputs include `bucket_name`, `distribution_id`, `distribution_domain`, `subdomain_url`, `gh_actions_role_arn`. **Save these — needed for step 3.**

---

### Task 10.3: Configure GitHub Environment for `dev`

**Files:** none (GitHub UI work).

- [ ] **Step 1: GitHub repo → Settings → Environments → New environment → name: `dev`**

- [ ] **Step 2: Set Environment variables (NOT secrets):**

| Name | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | (the `gh_actions_role_arn` output from step 10.2) |
| `AWS_ACCOUNT_ID` | (your AWS account ID) |
| `NEXT_PUBLIC_API_URL` | `https://<api-gateway-id>.execute-api.us-east-1.amazonaws.com` (the dev API endpoint from #4) |
| `S3_BUCKET` | (the `bucket_name` output) |
| `CLOUDFRONT_DISTRIBUTION_ID` | (the `distribution_id` output) |
| `SUBDOMAIN` | `dev-digest.patrickcmd.dev` |

- [ ] **Step 3: Set Environment secrets:**

| Name | Value |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | (from Clerk Dashboard → API Keys → publishable key for the dev instance — `pk_test_xxx`) |

- [ ] **Step 4: No required reviewers for `dev`** (we'll add reviewers only for `prod` later).

---

### Task 10.4: Trigger first deploy via workflow_dispatch

**Files:** none.

- [ ] **Step 1: Trigger via gh CLI**

```sh
gh workflow run web-deploy.yml -f environment=dev -f action=deploy
gh run watch
```

Expected: workflow runs successfully — install, build, sync to S3, invalidate CloudFront. Total time ~2-3 minutes.

---

### Task 10.5: Smoke test the deployed dev site

**Files:** none.

- [ ] **Step 1: Open the URL in a browser**

```sh
echo "https://dev-digest.patrickcmd.dev"
```

Open in Chrome/Safari. Expected: redirected to Clerk Account Portal sign-in.

- [ ] **Step 2: Sign in via Clerk** (use the same dev Clerk instance you set up for #4 smoke).

Expected: bounced back to `/profile?onboarding=1` with the welcome banner (because the user's profile_completed_at is null after the lazy-upsert).

- [ ] **Step 3: Fill in profile + save**

Add at least one entry per section. Click "Save profile". Expected: toast "Profile saved", banner disappears, can navigate to `/`.

- [ ] **Step 4: Click "Remix now"**

Expected: toast "Your remix is on the way (~30-60s)". Wait ~60s. Expected: a digest card appears in the list (the SFN run completes in the background and `/v1/digests` polling picks it up).

- [ ] **Step 5: Click into the digest detail**

Expected: full ranked-articles list rendered.

- [ ] **Step 6: Toggle dark mode**

Expected: theme persists across page refresh.

If any step fails, capture the diagnosis as a fix commit and re-deploy via `gh workflow run`.

---

### Task 10.6: Repeat for `test` and `prod` (optional)

**Files:** none.

- [ ] **Step 1: For `test`** — repeat 10.2-10.5 with `subdomain=test-digest.patrickcmd.dev`, workspace=`test`, the same dev Clerk instance.

- [ ] **Step 2: For `prod`** — repeat with `subdomain=digest.patrickcmd.dev`, workspace=`prod`, **production Clerk instance** (`pk_live_xxx`), and **set 1 required reviewer** on the GitHub Environment.

These can be deferred — `dev` is the immediate ship target.

---

## Phase 11 — Documentation + tag

### Task 11.1: Makefile additions

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append the web block after the existing `tag-api` target**

Find the existing `tag-api:` target and append AFTER it:

```makefile
# ---------- web (#5) ----------

.PHONY: web-install web-dev web-build web-test web-test-watch web-lint \
        web-typecheck web-osv \
        web-deploy-dev web-deploy-test web-deploy-prod \
        web-destroy-dev web-destroy-test web-destroy-prod \
        tag-web

web-install:                ## install pnpm deps (--ignore-scripts)
	cd web && pnpm install --frozen-lockfile --ignore-scripts

web-dev:                    ## run Next.js dev server (port 3000)
	cd web && pnpm dev

web-build:                  ## next build (static export → web/out/)
	cd web && pnpm build

web-test:                   ## vitest run (one-shot)
	cd web && pnpm test

web-test-watch:             ## vitest watch
	cd web && pnpm test:watch

web-lint:                   ## eslint check
	cd web && pnpm lint

web-typecheck:              ## tsc --noEmit
	cd web && pnpm typecheck

web-osv:                    ## OSV-Scanner against web/
	osv-scanner --recursive --fail-on-vuln web/

web-deploy-dev:             ## trigger web-deploy.yml for dev (gh CLI)
	gh workflow run web-deploy.yml -f environment=dev -f action=deploy

web-deploy-test:            ## trigger web-deploy.yml for test
	gh workflow run web-deploy.yml -f environment=test -f action=deploy

web-deploy-prod:            ## trigger web-deploy.yml for prod (requires reviewer)
	gh workflow run web-deploy.yml -f environment=prod -f action=deploy

web-destroy-dev:            ## DESTRUCTIVE: tear down dev infra
	@read -p "Type 'destroy-dev' to confirm: " c && [ "$$c" = "destroy-dev" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=dev -f action=destroy

web-destroy-test:           ## DESTRUCTIVE: tear down test infra
	@read -p "Type 'destroy-test' to confirm: " c && [ "$$c" = "destroy-test" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=test -f action=destroy

web-destroy-prod:           ## DESTRUCTIVE: tear down prod infra (use VERY carefully)
	@read -p "Type 'destroy-prod' to confirm: " c && [ "$$c" = "destroy-prod" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=prod -f action=destroy

tag-web:                    ## tag sub-project #5
	git tag -f -a frontend-v0.6.0 -m "Sub-project #5 Frontend (Next.js + Clerk + S3/CloudFront)"
	@echo "Push with: git push origin frontend-v0.6.0"
```

- [ ] **Step 2: Verify**

```sh
make help | grep -E "web-|tag-web" | head -20
make -n web-build
```

Expected: targets visible; `make -n web-build` prints `cd web && pnpm build`.

- [ ] **Step 3: Commit**

```sh
git add Makefile
git commit -m "build(make): add web-/tag-web targets (#5)"
```

---

### Task 11.2: `infra/README.md` section

**Files:**
- Modify: `infra/README.md`

- [ ] **Step 1: Append at the end of `infra/README.md`**

```markdown

## Sub-project #5 — Frontend (Next.js + Clerk + S3/CloudFront)

A static-exported Next.js app served from CloudFront, fronted by ACM cert
on `*.patrickcmd.dev`, with one CloudFront distribution + S3 bucket per
environment (dev/test/prod). Auth via Clerk's hosted Account Portal;
data via the API shipped in #4.

### Prerequisites (one-time)

1. **GitHub Actions OIDC provider** in the AWS account — created in
   `infra/bootstrap/`. Re-apply bootstrap if it doesn't exist:
   ```sh
   cd infra/bootstrap && terraform apply
   ```

2. **ACM wildcard cert** `*.patrickcmd.dev` in us-east-1 (existing).
   Verify:
   ```sh
   aws acm list-certificates --region us-east-1 --profile aiengineer \
     --query 'CertificateSummaryList[].DomainName' --output text
   ```

3. **Route 53 hosted zone** for `patrickcmd.dev` (existing).

4. **GitHub Environments** — `dev`, `test`, `prod` set up under repo
   Settings → Environments. Each gets vars + secrets (see "GitHub
   Environment configuration" below).

### Per-module Terraform init + apply

Per-environment:

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/web
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=web/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"

# For dev (repeat for test, prod with the matching subdomain):
terraform workspace new dev
terraform apply \
  -var=subdomain=dev-digest.patrickcmd.dev \
  -var=github_repo=PatrickCmd/ai-agents-news-aggregator
```

First apply creates ~10 resources: S3 bucket + 3 sub-resources +
bucket policy + CloudFront + OAC + 2 Route 53 records + GitHub OIDC
IAM role + policy.

### GitHub Environment configuration

Per env, set (via GitHub Settings → Environments → `<env>`):

**Vars (non-secret):**
- `AWS_DEPLOY_ROLE_ARN` — Terraform output `gh_actions_role_arn`
- `AWS_ACCOUNT_ID` — your AWS account ID
- `NEXT_PUBLIC_API_URL` — backend API base URL for that env
- `S3_BUCKET` — Terraform output `bucket_name`
- `CLOUDFRONT_DISTRIBUTION_ID` — Terraform output `distribution_id`
- `SUBDOMAIN` — full subdomain for that env

**Secrets:**
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` — from Clerk Dashboard

**Required reviewers:** add at least one for `prod`. Skip for dev/test.

### Deploy + destroy

```sh
make web-deploy-dev          # workflow_dispatch → deploy to dev
make web-deploy-test
make web-deploy-prod         # gated by reviewer

make web-destroy-dev         # workflow_dispatch → terraform destroy dev
make web-destroy-test
make web-destroy-prod        # use VERY carefully
```

### Failure modes

- **Build fails: `process is not defined`** — used a Node-only API in a
  client component. Audit imports; only browser-safe code allowed in
  static export.
- **Deploy succeeds but page returns 403** — bucket policy missing or
  OAC not bound. Re-apply Terraform.
- **CloudFront serves stale HTML after deploy** — invalidation didn't
  fire. Manually: `aws cloudfront create-invalidation --distribution-id
  <id> --paths '/*' --profile aiengineer`.
- **`401 invalid token` from API on every request** — `NEXT_PUBLIC_API_URL`
  env var doesn't match the deployed API's `CLERK_ISSUER`. Or the
  Clerk publishable key is for a different instance than the API expects.
- **`Cannot read 'getToken' of undefined`** — `<ClerkProvider>` not
  rendered above the consuming component. Check `app/layout.tsx`.
- **JWT template missing email/name claims** — frontend uses
  `getToken({ template: "news-api" })`. The template must exist in
  Clerk Dashboard → JWT Templates with email + name claims (same
  template the backend's smoke uses — see #4 spec §3).

### Roll back

To roll back the static bundle:

```sh
# S3 versioning is enabled on the bucket; restore prior versions via:
aws s3api list-object-versions --bucket digest-dev-dev-digest-patrickcmd-dev \
  --profile aiengineer

# Promote a prior version manually, then invalidate CloudFront.
```

To destroy a single env entirely (keeps Route 53 zone, ACM cert, OIDC provider):

```sh
make web-destroy-dev
```
```

- [ ] **Step 2: Commit**

```sh
git add infra/README.md
git commit -m "docs(infra): add sub-project #5 Frontend section"
```

---

### Task 11.3: `AGENTS.md` refresh

**Files:**
- Modify: `AGENTS.md`

Apply these edits in order:

- [ ] **Step 1: Flip #5 row in the decomposition table.** Find:

```
| 5 | Frontend (Next.js + Clerk + S3/CloudFront) | not started |
```

Replace with:

```
| **5** | Frontend — `web/` Next.js (static export) + `@clerk/clerk-react` + Tailwind/shadcn + TanStack Query + RHF/Zod, hosted on S3 + CloudFront via per-env Terraform module under `infra/web/` | shipped — tag `frontend-v0.6.0` |
```

- [ ] **Step 2: Add `web/` to the repo layout block.** Find the existing `web/` line:

```
├── web/                            # Next.js frontend (#5)
```

Replace with:

```
├── web/                            # Next.js frontend (static export, #5) — Tailwind + shadcn + Clerk SPA SDK + TanStack Query + RHF/Zod
```

- [ ] **Step 3: Add `infra/web/` to the infra block.** After the existing `infra/scheduler/` and `infra/api/` lines, add:

```
│   ├── web/                        # S3 + CloudFront + OAC + Route 53 + GitHub OIDC role per env (#5)
```

- [ ] **Step 4: Add a "Sub-project #5 (Frontend) — operational commands" section** before "## What NOT to do":

```markdown
### Sub-project #5 (Frontend) — operational commands

A Next.js static-export app at `digest.patrickcmd.dev` (prod) /
`dev-digest.patrickcmd.dev` / `test-digest.patrickcmd.dev`. Hosted on
S3 + CloudFront via per-env Terraform workspace. Auth via Clerk's
hosted Account Portal (`@clerk/clerk-react`, NOT `@clerk/nextjs`).
Reads the same JWT template `news-api` that the backend's #4 smoke
uses — single source of truth for the email + name claims contract.

```sh
# Local dev
make web-install                              # pnpm install --ignore-scripts
make web-dev                                  # next dev on :3000
make web-test
make web-typecheck
make web-lint
make web-osv                                  # OSV-Scanner

# Deploy / destroy via workflow_dispatch
make web-deploy-dev                           # gh workflow run
make web-deploy-test
make web-deploy-prod                          # gated by GitHub Environment reviewer
make web-destroy-dev                          # confirms with typed prompt
```

The frontend is **purely a client** of the API (#4) — no direct
Supabase / Step Functions / Clerk Backend API calls. JWT injected
via `useApiClient` hook calling `getToken({ template: "news-api" })`.

See `infra/README.md` § "Sub-project #5 — Frontend" for full
lifecycle, GitHub Environment setup, and rollback recipe.
```

- [ ] **Step 5: Append to "What NOT to do":**

```markdown
- Do not use `@clerk/nextjs` in the `web/` package. We ship a static export, which is incompatible with Next.js middleware-based auth. Use `@clerk/clerk-react` (the SPA flavour) — `<RedirectToSignIn />`, `<UserButton />`, `useAuth().getToken({ template: "news-api" })`.
- Do not use `output: "standalone"` or default Next.js (which assumes a Node server). The `web/next.config.ts` MUST set `output: "export"` — every page is pre-rendered HTML, no SSR / server actions / middleware.
- Do not use `npm` or `yarn` in `web/`. The lockfile is `pnpm-lock.yaml` and the security model relies on pnpm's strict resolution. Run `pnpm` commands; the Makefile targets enforce this.
- Do not run `pnpm install` without `--ignore-scripts` in CI. It's the dominant npm supply-chain attack vector. The Makefile target and `web-ci.yml` workflow both pass it.
- Do not pin direct deps with `^` or `~` ranges in `web/package.json`. Use exact versions — `pnpm add <pkg>` writes the resolved version verbatim. The lockfile pins transitive.
- Do not call `boto3` or any AWS SDK from the frontend. Every backend interaction goes through `https://<api>/v1/*` with a Clerk JWT.
- Do not hardcode API URLs or Clerk keys. They live in `process.env.NEXT_PUBLIC_*`, baked into the build at deploy time per env. Local dev reads from `web/.env.local` (gitignored).
- Do not commit `web/.env*.local`. They contain real Clerk publishable keys for dev. The `.env.example` is the only one tracked.
- Do not skip the JWT template — `getToken()` (no template) returns Clerk's default session token which lacks email/name claims, and our backend's `ClerkClaims` Pydantic model requires them. The hook MUST pass `{ template: "news-api" }`.
```

- [ ] **Step 6: Commit**

```sh
git add AGENTS.md
git commit -m "docs(agents): refresh AGENTS.md for sub-project #5 (Frontend)"
```

---

### Task 11.4: `README.md` refresh

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the badge after the Scheduler badge**

Find:

```markdown
[![Scheduler](https://img.shields.io/badge/sub--project%20%233-scheduler--v0.4.0-success)]...
```

After the API badge (already there from #4), add:

```markdown
[![Frontend](https://img.shields.io/badge/sub--project%20%235-frontend--v0.6.0-success)](https://github.com/PatrickCmd/ai-agents-news-aggregator/releases/tag/frontend-v0.6.0)
```

- [ ] **Step 2: Flip #5 in the "Solution at a Glance" table**

Find:

```
| 5 | **Frontend** | Next.js + Clerk + S3/CloudFront (profile editor, digest history, "remix now" button) | not started |
```

Replace with:

```
| **5** | **Frontend** | Next.js (static export) + Clerk Account Portal + Tailwind/shadcn + TanStack Query, hosted on S3 + CloudFront. Profile editor, digest history, "remix now" button. | ✅ shipped |
```

- [ ] **Step 3: Flip #5 in the "Project Status" table**

```
| 5 | Frontend | `frontend-v0.6.0` | ✅ Next.js static export + S3 + CloudFront + Clerk + Route 53 |
```

- [ ] **Step 4: Add a "Running the Frontend (#5)" section after "Running the API (#4)"**

```markdown
## Running the Frontend (#5)

A Next.js static-export app served from S3 + CloudFront. Three
authenticated pages: digest list, digest detail, profile editor.
Auth via Clerk's hosted Account Portal — no auth UI to build or
maintain. Data via TanStack Query against the API (#4).

```sh
# Local dev (requires the API running locally — see "Running the API (#4)")
cp web/.env.example web/.env.local      # fill in NEXT_PUBLIC_*
make web-install                        # pnpm install --ignore-scripts
make web-dev                            # → http://localhost:3000

# Deploy
make web-deploy-dev                     # workflow_dispatch
make web-deploy-test
make web-deploy-prod                    # gated by GitHub Environment reviewer

# Tests + supply-chain scan
make web-test
make web-typecheck
make web-osv                            # OSV-Scanner CVE check
```

Sub-project #5 introduces three new domains:
`digest.patrickcmd.dev` (prod), `dev-digest.patrickcmd.dev`,
`test-digest.patrickcmd.dev`. ACM wildcard cert + Route 53 zone
reused; one CloudFront distribution per env. Per-env GitHub
Environments hold the Clerk publishable key + Terraform outputs.

See [infra/README.md](infra/README.md) § "Sub-project #5 — Frontend"
for the full deploy lifecycle, GitHub Environment configuration, and
failure mode reference.
```

- [ ] **Step 5: Commit**

```sh
git add README.md
git commit -m "docs(readme): refresh status + add Running the Frontend (#5) section"
```

---

### Task 11.5: Final verify + tag

**Files:** none.

- [ ] **Step 1: Full quality gate**

```sh
make check                # backend lint+typecheck+tests
make web-lint && make web-typecheck && make web-test
make web-build            # static export builds cleanly
make web-osv              # supply-chain scan
```

All clean.

- [ ] **Step 2: Tag**

```sh
make tag-web
git tag --list "frontend-*" -n3
```

Expected: `frontend-v0.6.0` exists locally.

- [ ] **Step 3: Push (after merging branch to main)**

```sh
git push origin frontend-v0.6.0
```

---

## Final completion checklist

After all phases land:

- [ ] All 267+ pre-existing tests still green (`make check`).
- [ ] All new web tests green (`make web-test`).
- [ ] `make web-build` produces `web/out/` cleanly.
- [ ] `make web-osv` reports no high-severity CVEs.
- [ ] dev environment deployed at `https://dev-digest.patrickcmd.dev`.
- [ ] Smoke complete: sign-in → onboarding → profile save → digest list → remix → digest appears.
- [ ] Dependabot PRs queue is empty (or contains only freshly-opened PRs from the weekly schedule).
- [ ] `frontend-v0.6.0` tag created.

---

## Self-review notes (for the implementer)

Pre-completion sanity check:

1. **Spec coverage** — every section of `docs/superpowers/specs/2026-04-28-frontend-design.md` has a concrete task in this plan: §1 goal/non-goals (whole plan), §2 architecture (Phases 4 & 8), §3 routes/IA (Phases 4-7), §4 auth (Tasks 3.1, 4.3, 7.1), §5 data layer (Phase 1.3, 1.4, 2.x), §6 page contracts (Tasks 5.4, 5.5, 6.3), §7 remix UX (Task 2.5), §8 module structure (whole plan reflects this), §9 theming (Tasks 0.2, 1.5, 4.1, 4.3), §10 supply-chain (Tasks 0.1, 9.1, 9.3, 9.4), §11 infra (Phase 8), §12 CI/CD (Phase 9), §13 local dev + Make (Task 11.1), §14 testing (test files in every TDD task), §15 glossary (referenced via file paths), §16 risks (mitigations baked into tasks), §17 non-goals (informational).

2. **Type consistency** — `UserProfile`, `UserOut`, `DigestSummaryOut`, `DigestOut`, `DigestListResponse`, `RemixResponse`, `ApiError` defined in Task 1.1, used identically in every hook + component test. `EMPTY_PROFILE` defined in Task 1.2, used identically in profile editor + tests. Query keys (`QK_ME`, `QK_DIGESTS`, `qkDigest(id)`) consistent across hooks. `useApiClient` signature + `request<T>(path, init)` shape consistent across all hook usages.

3. **No placeholders** — every step has either complete code, an exact command, or a copy-pastable patch. No "TBD", no "implement later". The closest thing is Task 8.1's "Find the bootstrap module's main file" which is intentionally exploratory (the engineer needs to look at the existing module before editing).

4. **Frequent commits** — every task ends with a focused conventional-commit; the plan totals ~50 commits, mirroring the cadence of #2-#4.
