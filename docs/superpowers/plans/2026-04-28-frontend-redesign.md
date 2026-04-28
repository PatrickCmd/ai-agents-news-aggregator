# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the editorial × terminal redesign defined in [2026-04-28-frontend-redesign.md](../specs/2026-04-28-frontend-redesign.md): fix the broken Tailwind v4 setup, ship a public landing page, restructure routing so `/` is public, redesign the digest list and detail with Fraunces + Geist + Geist Mono on a warm-amber-on-dark palette, and add YouTube preview rendering for video sources.

**Architecture:** Tailwind v4-only `globals.css` with one OKLCH token system; three Google Fonts loaded via `next/font/google`; default-dark theme provider with `.light` opt-in; root `app/page.tsx` branches on `useAuth().isSignedIn` between `<LandingHero />` and the editorial digest list (no middleware — incompatible with static export); private routes (`/digest`, `/profile`) move into a new `(private)` route group that owns `<RequireAuth>` + `<OnboardingGate>`; YouTube detection is a pure URL-pattern function with full unit coverage; integration into `<RankedArticleCard>` is a single conditional render.

**Tech Stack:** Next.js 16.2.4 (static export), React 19.2.5, Tailwind v4 (4.2.4), shadcn/ui (radix-nova preset), `@clerk/react` 6.4.5, `@tanstack/react-query` 5.100.5, `next/font/google` (Fraunces, Geist, Geist Mono), Vitest + RTL.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| [web/app/globals.css](../../../web/app/globals.css) | rewrite | Tailwind v4-only imports; OKLCH design tokens (one source of truth); shadcn token aliases via `@theme inline`; base layer for body / headings |
| [web/app/layout.tsx](../../../web/app/layout.tsx) | modify | Load Fraunces + Geist + Geist Mono via `next/font/google`; mount font variables on `<html>`; flip FOUC script to add `.light` instead of `.dark` |
| [web/app/providers.tsx](../../../web/app/providers.tsx) | unchanged | Provider stack (Clerk → Theme → Query). No change. |
| [web/lib/theme.tsx](../../../web/lib/theme.tsx) | rewrite | Default theme `dark`; toggle adds/removes `.light` class on `<html>`; same external API |
| [web/app/page.tsx](../../../web/app/page.tsx) | new | Public root; branches on `useAuth().isSignedIn` between `<LandingHero />` and the editorial digest list |
| [web/app/(private)/layout.tsx](../../../web/app/(private)/layout.tsx) | new (renamed) | `<RequireAuth>` + `<OnboardingGate>` — gates `/digest` and `/profile` |
| [web/app/(private)/digest/page.tsx](../../../web/app/(private)/digest/page.tsx) | move + restyle | Digest detail with editorial banner + ranked article cards |
| [web/app/(private)/profile/page.tsx](../../../web/app/(private)/profile/page.tsx) | move + restyle | Profile editor (functional contract unchanged, visual restyle) |
| [web/app/(authenticated)/](../../../web/app/(authenticated)/) | delete | Replaced by root `page.tsx` + `(private)/` group |
| [web/components/layout/Logo.tsx](../../../web/components/layout/Logo.tsx) | new | `digest.` typographic mark — Fraunces, accent period |
| [web/components/layout/Header.tsx](../../../web/components/layout/Header.tsx) | modify | Use `<Logo />`; tighten layout; preserve theme toggle + UserButton |
| [web/components/layout/Footer.tsx](../../../web/components/layout/Footer.tsx) | rewrite | Mono ribbon: `daily · ai-curated · ranked 0–100 · ~5 min read` |
| [web/components/landing/LandingHero.tsx](../../../web/components/landing/LandingHero.tsx) | new | Asymmetric public landing — left headline + CTAs, right tilted sample digest, below-fold "How it works" |
| [web/components/landing/SampleDigestCard.tsx](../../../web/components/landing/SampleDigestCard.tsx) | new | Static-fixture digest preview tilted -2°; visual only |
| [web/components/digest/DigestRow.tsx](../../../web/components/digest/DigestRow.tsx) | new | Editorial newsletter row — mono date rail + Fraunces title + themes-as-text |
| [web/components/digest/DigestCard.tsx](../../../web/components/digest/DigestCard.tsx) | delete | Replaced by `<DigestRow />` |
| [web/components/digest/DigestListSection.tsx](../../../web/components/digest/DigestListSection.tsx) | new | Editorial digest-list body — header band + DigestRow list + remix CTA + load-more (consumed by root `/` when signed in) |
| [web/components/digest/RankedArticleCard.tsx](../../../web/components/digest/RankedArticleCard.tsx) | rewrite | Card with rank/score gutter, pulled-quote "why" block, optional YouTube preview above title |
| [web/components/digest/YouTubePreview.tsx](../../../web/components/digest/YouTubePreview.tsx) | new | Privacy-enhanced (`youtube-nocookie.com`) iframe + "Open on YouTube ↗" |
| [web/components/digest/EmptyState.tsx](../../../web/components/digest/EmptyState.tsx) | rewrite | Restyle — Fraunces title, mono caption |
| [web/components/digest/DigestDetailSkeleton.tsx](../../../web/components/digest/DigestDetailSkeleton.tsx) | rewrite | Match new editorial detail layout |
| [web/components/digest/DigestListSkeleton.tsx](../../../web/components/digest/DigestListSkeleton.tsx) | rewrite | Match new list-row layout |
| [web/lib/utils/youtube.ts](../../../web/lib/utils/youtube.ts) | new | `youtubeIdFromUrl(url: string): string \| null` — pure URL detection |
| [web/lib/utils/youtube.test.ts](../../../web/lib/utils/youtube.test.ts) | new | Unit tests covering watch / youtu.be / shorts / embed / non-YouTube |
| [web/components/digest/__tests__/YouTubePreview.test.tsx](../../../web/components/digest/__tests__/YouTubePreview.test.tsx) | new | Renders iframe + open-link |
| [web/components/landing/__tests__/LandingHero.test.tsx](../../../web/components/landing/__tests__/LandingHero.test.tsx) | new | Renders CTAs + How-it-works |
| [web/app/__tests__/page.test.tsx](../../../web/app/__tests__/page.test.tsx) | new | Auth branch — signed-in shows list, signed-out shows landing |

---

## Phase 0 — CSS foundation

### Task 0.1: Rewrite `globals.css` to Tailwind v4 only

**Files:**
- Rewrite: [web/app/globals.css](../../../web/app/globals.css)

- [ ] **Step 1: Replace the entire file with the v4-only version**

```css
@import "tailwindcss";
@import "tw-animate-css";

/* Dark is the default. .light opts into light mode. We invert shadcn's
   standard `dark:` variant so it fires by default (when html does NOT
   have .light), and add a `light:` variant for the inverse. This keeps
   pre-existing shadcn `dark:foo` overrides in components like
   <Badge> firing on the dark default. */
@custom-variant dark (&:where(html:not(.light), html:not(.light) *));
@custom-variant light (&:where(html.light, html.light *));

@theme inline {
  --color-background: var(--bg);
  --color-foreground: var(--ink);
  --color-card: var(--surface);
  --color-card-foreground: var(--ink);
  --color-popover: var(--surface);
  --color-popover-foreground: var(--ink);
  --color-primary: var(--accent);
  --color-primary-foreground: var(--accent-ink);
  --color-secondary: var(--surface-2);
  --color-secondary-foreground: var(--ink);
  --color-muted: var(--surface-2);
  --color-muted-foreground: var(--ink-dim);
  --color-accent: var(--surface-2);
  --color-accent-foreground: var(--ink);
  --color-destructive: var(--danger);
  --color-destructive-foreground: var(--ink);
  --color-border: var(--rule);
  --color-input: var(--rule);
  --color-ring: var(--accent);

  --font-display: "Fraunces Variable", "Fraunces", ui-serif, Georgia, "Times New Roman", serif;
  --font-sans: "Geist Variable", "Geist", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono Variable", "Geist Mono", ui-monospace, "JetBrains Mono", "Menlo", monospace;

  --radius: 0.5rem;
  --radius-sm: calc(var(--radius) * 0.6);
  --radius-md: calc(var(--radius) * 0.8);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) * 1.4);
  --radius-2xl: calc(var(--radius) * 1.8);
  --radius-3xl: calc(var(--radius) * 2.2);
  --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
  --bg: oklch(0.16 0.012 245);
  --surface: oklch(0.20 0.014 245);
  --surface-2: oklch(0.23 0.014 245);
  --ink: oklch(0.96 0.018 80);
  --ink-dim: oklch(0.66 0.012 80);
  --rule: oklch(0.30 0.012 245);
  --accent: oklch(0.78 0.16 65);
  --accent-ink: oklch(0.18 0.020 65);
  --danger: oklch(0.65 0.20 25);
}

.light {
  --bg: oklch(0.98 0.006 80);
  --surface: oklch(0.96 0.008 80);
  --surface-2: oklch(0.93 0.010 80);
  --ink: oklch(0.18 0.012 245);
  --ink-dim: oklch(0.42 0.010 245);
  --rule: oklch(0.86 0.010 245);
  --accent: oklch(0.62 0.18 65);
  --accent-ink: oklch(0.98 0.006 80);
  --danger: oklch(0.55 0.20 25);
}

@layer base {
  * {
    border-color: var(--color-border);
    outline-color: color-mix(in oklch, var(--color-ring) 50%, transparent);
  }
  html {
    font-family: var(--font-sans);
  }
  body {
    background-color: var(--color-background);
    color: var(--color-foreground);
    font-feature-settings: "ss01", "cv11";
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  h1, h2, h3, h4 {
    font-family: var(--font-display);
    letter-spacing: -0.02em;
    font-weight: 600;
  }
  /* Mono utility for any tabular metadata. */
  .font-mono, code, kbd, samp, pre {
    font-family: var(--font-mono);
    font-feature-settings: "ss02", "cv02";
  }
}

@layer utilities {
  .container {
    width: 100%;
    margin-inline: auto;
    padding-inline: 1.25rem;
    max-width: 72rem;
  }
  @media (min-width: 768px) {
    .container { padding-inline: 2rem; }
  }
  .text-balance { text-wrap: balance; }
  .text-pretty { text-wrap: pretty; }
}
```

- [ ] **Step 2: Verify the dev server boots without CSS parse errors**

Run: `cd web && pnpm dev` (in a separate terminal — leave it running)
Expected: `▲ Next.js 16.2.4 ... Local: http://localhost:3000` with no CSS errors in stderr.

- [ ] **Step 3: Commit**

```bash
git add web/app/globals.css
git commit -m "style(web): rewrite globals.css for tailwind v4 + editorial tokens"
```

---

### Task 0.2: Load fonts and flip FOUC script in `app/layout.tsx`

**Files:**
- Modify: [web/app/layout.tsx](../../../web/app/layout.tsx)

- [ ] **Step 1: Replace the file**

```tsx
import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-fraunces",
  axes: ["opsz", "SOFT", "WONK"],
});

const geist = Geist({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "digest.",
  description: "AI engineers ship faster when they read less. digest. ranks the 10 articles you actually need from ~80 daily sources.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${fraunces.variable} ${geist.variable} ${geistMono.variable}`}
    >
      <head>
        {/* Default = dark. Apply .light before hydration to prevent FOUC. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function() {
              try {
                var t = localStorage.getItem('theme') || 'dark';
                var light = t === 'light' || (t === 'system' && window.matchMedia('(prefers-color-scheme: light)').matches);
                if (light) document.documentElement.classList.add('light');
              } catch (e) {}
            })();`,
          }}
        />
      </head>
      <body className="min-h-screen flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Update `globals.css` font fallbacks to use the variable names**

The `next/font/google` package mounts each font as a CSS variable on the element it's applied to. Update the `--font-display`, `--font-sans`, `--font-mono` lines in [web/app/globals.css](../../../web/app/globals.css) to consume those variables. Replace this block:

```css
  --font-display: "Fraunces Variable", "Fraunces", ui-serif, Georgia, "Times New Roman", serif;
  --font-sans: "Geist Variable", "Geist", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono Variable", "Geist Mono", ui-monospace, "JetBrains Mono", "Menlo", monospace;
```

with:

```css
  --font-display: var(--font-fraunces), ui-serif, Georgia, "Times New Roman", serif;
  --font-sans: var(--font-geist), ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-mono: var(--font-geist-mono), ui-monospace, "JetBrains Mono", "Menlo", monospace;
```

> **Why not literal fontstack strings?** The shadcn skill warns about `--font-sans: var(--font-sans)` self-references. Here the chain is `--font-sans` (Tailwind theme) → `var(--font-geist)` (next/font runtime variable) — different identifier, no cycle. This is the supported pattern for `next/font` + Tailwind v4.

- [ ] **Step 3: Verify in browser**

Open [http://localhost:3000](http://localhost:3000) — body text should be Geist (clean grotesque), not the system default. View source on `<html>` and confirm `class="__variable_xxx __variable_yyy __variable_zzz"` is present.

- [ ] **Step 4: Commit**

```bash
git add web/app/layout.tsx web/app/globals.css
git commit -m "feat(web): load fraunces + geist + geist mono via next/font"
```

---

### Task 0.3: Flip `theme.tsx` to default-dark + `.light` opt-in

**Files:**
- Rewrite: [web/lib/theme.tsx](../../../web/lib/theme.tsx)

- [ ] **Step 1: Write a failing test for default theme**

Create [web/lib/__tests__/theme.test.tsx](../../../web/lib/__tests__/theme.test.tsx):

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "@/lib/theme";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <button data-testid="probe" data-theme={theme} onClick={() => setTheme("light")}>
      flip
    </button>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    document.documentElement.className = "";
    localStorage.clear();
  });

  it("defaults to dark and does not add a class to <html>", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.classList.contains("light")).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("adds .light to <html> when setTheme('light') is called", () => {
    const { getByTestId } = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("removes .light when flipping back to dark", () => {
    const { getByTestId, rerender } = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(true);

    function Probe2() {
      const { setTheme } = useTheme();
      return <button data-testid="probe2" onClick={() => setTheme("dark")}>back</button>;
    }
    rerender(
      <ThemeProvider>
        <Probe2 />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe2").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });
});
```

- [ ] **Step 2: Run the test — should fail because `theme.tsx` still defaults to system + adds `.dark`**

Run: `cd web && pnpm test -- theme.test`
Expected: FAIL — current code adds `.dark` to `<html>` instead of conditionally adding `.light`.

- [ ] **Step 3: Rewrite `lib/theme.tsx`**

```tsx
"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type React from "react";

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
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : theme;
  if (resolved === "light") root.classList.add("light");
  else root.classList.remove("light");
}

export function ThemeProvider({ children }: { children: ReactNode }): React.ReactElement {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "dark";
  });

  useEffect(() => {
    applyTheme(theme);
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: light)");
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

- [ ] **Step 4: Re-run the test**

Run: `cd web && pnpm test -- theme.test`
Expected: PASS — all 3 cases.

- [ ] **Step 5: Update [web/components/layout/ThemeToggle.tsx](../../../web/components/layout/ThemeToggle.tsx) icon logic**

Read the file first:

```bash
cat web/components/layout/ThemeToggle.tsx
```

If it shows a sun icon when `theme === "light"`, the visual is correct. If it shows the icon by checking `document.documentElement.classList.contains("dark")`, change that check to `!document.documentElement.classList.contains("light")` to match the new convention. (Most likely it uses `theme` from `useTheme()` — no change needed.)

- [ ] **Step 6: Commit**

```bash
git add web/lib/theme.tsx web/lib/__tests__/theme.test.tsx web/components/layout/ThemeToggle.tsx
git commit -m "refactor(web): default theme to dark, .light class for opt-in"
```

---

## Phase 1 — Brand chrome

### Task 1.1: Create the `<Logo />` typographic mark

**Files:**
- Create: [web/components/layout/Logo.tsx](../../../web/components/layout/Logo.tsx)

- [ ] **Step 1: Create the file**

```tsx
import Link from "next/link";

export function Logo({ as = "link" }: { as?: "link" | "static" } = {}) {
  const inner = (
    <span className="font-display text-xl font-semibold leading-none tracking-tight">
      digest<span className="text-primary">.</span>
    </span>
  );
  if (as === "static") return inner;
  return (
    <Link href="/" aria-label="digest. — go to home" className="inline-block">
      {inner}
    </Link>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/layout/Logo.tsx
git commit -m "feat(web): typographic <Logo /> mark"
```

---

### Task 1.2: Restyle `<Header />`

**Files:**
- Modify: [web/components/layout/Header.tsx](../../../web/components/layout/Header.tsx)

- [ ] **Step 1: Replace the file**

```tsx
"use client";

import { UserButton } from "@clerk/react";
import { Logo } from "@/components/layout/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-[var(--rule)] bg-[color-mix(in_oklch,var(--bg)_88%,transparent)] backdrop-blur supports-[backdrop-filter]:bg-[color-mix(in_oklch,var(--bg)_70%,transparent)]">
      <div className="container flex h-16 items-center justify-between">
        <Logo />
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <UserButton appearance={{ elements: { avatarBox: "h-8 w-8" } }} />
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Verify in browser**

Reload [http://localhost:3000](http://localhost:3000) — header should now be 64px tall, "digest." appears in Fraunces with an amber period, theme toggle and user button align right.

- [ ] **Step 3: Commit**

```bash
git add web/components/layout/Header.tsx
git commit -m "feat(web): editorial header with logo + sticky blur"
```

---

### Task 1.3: Mono ribbon `<Footer />`

**Files:**
- Rewrite: [web/components/layout/Footer.tsx](../../../web/components/layout/Footer.tsx)

- [ ] **Step 1: Replace the file**

```tsx
export function Footer() {
  return (
    <footer className="mt-auto border-t border-[var(--rule)]">
      <div className="container flex flex-col items-center justify-between gap-2 py-4 text-xs sm:flex-row">
        <p className="font-mono uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          daily · ai-curated · ranked 0–100 · ~5 min read
        </p>
        <p className="font-mono text-[var(--ink-dim)]">v0.6.0</p>
      </div>
    </footer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/layout/Footer.tsx
git commit -m "feat(web): mono ribbon footer"
```

---

## Phase 2 — YouTube preview (TDD)

### Task 2.1: `youtubeIdFromUrl` pure function

**Files:**
- Create: [web/lib/utils/youtube.ts](../../../web/lib/utils/youtube.ts)
- Create: [web/lib/utils/youtube.test.ts](../../../web/lib/utils/youtube.test.ts)

- [ ] **Step 1: Write the failing test first**

Create [web/lib/utils/youtube.test.ts](../../../web/lib/utils/youtube.test.ts):

```ts
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
```

- [ ] **Step 2: Run the test — should fail**

Run: `cd web && pnpm test -- youtube.test`
Expected: FAIL with `Cannot find module '@/lib/utils/youtube'`.

- [ ] **Step 3: Implement `youtubeIdFromUrl`**

Create [web/lib/utils/youtube.ts](../../../web/lib/utils/youtube.ts):

```ts
const YT_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "youtu.be",
  "www.youtu.be",
]);

const ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function youtubeIdFromUrl(url: string): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (!YT_HOSTS.has(parsed.hostname)) return null;

  // youtu.be/<id>[?t=...]
  if (parsed.hostname === "youtu.be" || parsed.hostname === "www.youtu.be") {
    const id = parsed.pathname.slice(1).split("/")[0];
    return ID_RE.test(id) ? id : null;
  }

  // youtube.com/watch?v=<id>
  if (parsed.pathname === "/watch") {
    const id = parsed.searchParams.get("v");
    return id && ID_RE.test(id) ? id : null;
  }

  // youtube.com/shorts/<id> or /embed/<id>
  const m = parsed.pathname.match(/^\/(?:shorts|embed)\/([^/?]+)/);
  if (m && ID_RE.test(m[1])) return m[1];

  return null;
}
```

- [ ] **Step 4: Re-run the test**

Run: `cd web && pnpm test -- youtube.test`
Expected: PASS — all 10 cases.

- [ ] **Step 5: Commit**

```bash
git add web/lib/utils/youtube.ts web/lib/utils/youtube.test.ts
git commit -m "feat(web): youtubeIdFromUrl URL detection helper"
```

---

### Task 2.2: `<YouTubePreview />` component

**Files:**
- Create: [web/components/digest/YouTubePreview.tsx](../../../web/components/digest/YouTubePreview.tsx)
- Create: [web/components/digest/__tests__/YouTubePreview.test.tsx](../../../web/components/digest/__tests__/YouTubePreview.test.tsx)

- [ ] **Step 1: Write the failing test**

Create [web/components/digest/__tests__/YouTubePreview.test.tsx](../../../web/components/digest/__tests__/YouTubePreview.test.tsx):

```tsx
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
  });

  it("renders an Open on YouTube escape link", () => {
    render(<YouTubePreview videoId="dQw4w9WgXcQ" title="Never gonna" />);
    const link = screen.getByRole("link", { name: /open on youtube/i }) as HTMLAnchorElement;
    expect(link.href).toBe("https://youtu.be/dQw4w9WgXcQ");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noopener");
  });
});
```

- [ ] **Step 2: Run the test — should fail**

Run: `cd web && pnpm test -- YouTubePreview.test`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement the component**

Create [web/components/digest/YouTubePreview.tsx](../../../web/components/digest/YouTubePreview.tsx):

```tsx
import { ExternalLinkIcon } from "lucide-react";

interface Props {
  videoId: string;
  title: string;
}

export function YouTubePreview({ videoId, title }: Props) {
  return (
    <div className="space-y-2">
      <div className="aspect-video w-full overflow-hidden rounded-md border border-[var(--rule)] bg-black">
        <iframe
          title={title}
          src={`https://www.youtube-nocookie.com/embed/${videoId}`}
          loading="lazy"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
          className="h-full w-full"
        />
      </div>
      <a
        href={`https://youtu.be/${videoId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.14em] text-[var(--ink-dim)] hover:text-[var(--ink)] transition-colors"
      >
        <ExternalLinkIcon className="h-3 w-3" />
        Open on YouTube
      </a>
    </div>
  );
}
```

- [ ] **Step 4: Re-run the test**

Run: `cd web && pnpm test -- YouTubePreview.test`
Expected: PASS — both cases.

- [ ] **Step 5: Commit**

```bash
git add web/components/digest/YouTubePreview.tsx web/components/digest/__tests__/YouTubePreview.test.tsx
git commit -m "feat(web): privacy-enhanced YouTubePreview component"
```

---

### Task 2.3: Integrate `<YouTubePreview />` into `<RankedArticleCard />`

**Files:**
- Rewrite: [web/components/digest/RankedArticleCard.tsx](../../../web/components/digest/RankedArticleCard.tsx)

- [ ] **Step 1: Replace the file**

```tsx
import { Card, CardContent } from "@/components/ui/card";
import { YouTubePreview } from "@/components/digest/YouTubePreview";
import { youtubeIdFromUrl } from "@/lib/utils/youtube";
import type { RankedArticle } from "@/lib/types/api";

export function RankedArticleCard({ article, rank }: { article: RankedArticle; rank: number }) {
  const ytId = youtubeIdFromUrl(article.url);

  return (
    <Card className="overflow-hidden">
      <CardContent className="grid grid-cols-12 gap-4 px-4 py-5 sm:gap-6 sm:px-6 sm:py-6">
        {/* Left gutter — rank + score chip */}
        <div className="col-span-2 flex flex-col items-start gap-2 sm:col-span-1">
          <span className="font-display text-3xl leading-none text-[var(--ink-dim)]">
            {rank}
          </span>
          <span
            className="inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded-sm bg-primary px-1.5 font-mono text-[0.78rem] tabular-nums leading-none tracking-tight text-primary-foreground"
            aria-label={`Score: ${article.score} out of 100`}
          >
            {article.score}
          </span>
        </div>

        {/* Body */}
        <div className="col-span-10 space-y-3 sm:col-span-11">
          {ytId && <YouTubePreview videoId={ytId} title={article.title} />}
          <h3 className="text-balance">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-display text-xl font-semibold leading-snug text-[var(--ink)] underline-offset-4 hover:underline"
            >
              {article.title}
            </a>
          </h3>
          <p className="text-pretty text-[0.95rem] leading-relaxed text-[var(--ink)]/90">
            {article.summary}
          </p>
          <blockquote className="border-l-2 border-primary pl-4 text-sm italic leading-relaxed text-[var(--ink-dim)]">
            <span className="not-italic font-mono text-[0.7rem] uppercase tracking-[0.18em] text-[var(--ink-dim)]/80">
              Why this article
            </span>
            <p className="mt-1">{article.why_ranked}</p>
          </blockquote>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify the existing detail page still works**

Run: `cd web && pnpm dev` (if not already running) and open [http://localhost:3000/digest?id=8](http://localhost:3000/digest?id=8) (signed-in). The article cards should render with the new gutter layout. If a YouTube article is in the digest, the embed should appear above the title.

- [ ] **Step 3: Commit**

```bash
git add web/components/digest/RankedArticleCard.tsx
git commit -m "feat(web): editorial article card with score gutter + YouTube embed"
```

---

## Phase 3 — Digest detail editorial layout

### Task 3.1: Restyle `<DigestDetailSkeleton />`

**Files:**
- Rewrite: [web/components/digest/DigestDetailSkeleton.tsx](../../../web/components/digest/DigestDetailSkeleton.tsx)

- [ ] **Step 1: Replace the file**

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function DigestDetailSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      <div className="space-y-3">
        <Skeleton className="h-3 w-48" />
        <Skeleton className="h-12 w-3/4" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <Skeleton className="h-20 w-full" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] pt-6">
          <div className="col-span-2 sm:col-span-1 space-y-2">
            <Skeleton className="h-7 w-7" />
            <Skeleton className="h-5 w-9" />
          </div>
          <div className="col-span-10 sm:col-span-11 space-y-2">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/digest/DigestDetailSkeleton.tsx
git commit -m "style(web): editorial DigestDetailSkeleton"
```

---

### Task 3.2: Rewrite the digest detail page (new path under `(private)`)

**Files:**
- Move: [web/app/(authenticated)/digest/page.tsx](../../../web/app/(authenticated)/digest/page.tsx) → [web/app/(private)/digest/page.tsx](../../../web/app/(private)/digest/page.tsx)
- Rewrite content during the move.

> **Note:** The route group rename happens in Task 5.3. For this task, edit in place at the current path; the rename is a separate concern.

- [ ] **Step 1: Replace [web/app/(authenticated)/digest/page.tsx](../../../web/app/(authenticated)/digest/page.tsx)**

```tsx
"use client";

import { useSearchParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useDigest } from "@/lib/hooks/useDigest";
import { RankedArticleCard } from "@/components/digest/RankedArticleCard";
import { DigestDetailSkeleton } from "@/components/digest/DigestDetailSkeleton";
import { ApiError } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${fmt(start)} — ${fmt(end)}`;
}

export default function DigestDetailPage() {
  const params = useSearchParams();
  const idParam = params.get("id");
  const numericId = idParam ? Number(idParam) : NaN;
  const idValid = Number.isFinite(numericId);

  const { data, isLoading, error } = useDigest(idValid ? numericId : 0);

  if (!idValid) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-3xl">
        <AlertDescription>Missing or invalid digest id.</AlertDescription>
      </Alert>
    );
  }

  if (isLoading) return <DigestDetailSkeleton />;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-3xl">
        <AlertDescription>Digest not found.</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <article className="mx-auto max-w-3xl space-y-8 py-6">
      <header className="space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          {formatPeriod(data.period_start, data.period_end)}
        </p>
        <h1 className="text-balance font-display text-5xl leading-[1.05]">
          Your digest<span className="text-primary">.</span>
        </h1>
        {data.top_themes.length > 0 && (
          <p className="text-sm text-[var(--ink-dim)]">
            {data.top_themes.join(" · ")}
          </p>
        )}
      </header>

      {data.intro && (
        <p className="text-pretty text-lg leading-relaxed text-[var(--ink)]/90">
          {data.intro}
        </p>
      )}

      <ol className="list-none space-y-4 p-0">
        {data.ranked_articles.map((a, i) => (
          <li key={a.article_id}>
            <RankedArticleCard article={a} rank={i + 1} />
          </li>
        ))}
      </ol>
    </article>
  );
}
```

- [ ] **Step 2: Verify the page in browser**

Open [http://localhost:3000/digest?id=8](http://localhost:3000/digest?id=8) (signed-in). Expect: mono date strip, "Your digest." in oversized Fraunces with amber period, themes as `·`-separated text (no broken pills), intro paragraph, then ranked-article cards.

- [ ] **Step 3: Commit**

```bash
git add web/app/\(authenticated\)/digest/page.tsx
git commit -m "feat(web): editorial digest detail page (banner + themes-as-text)"
```

---

## Phase 4 — Authenticated home

### Task 4.1: New `<DigestRow />` newsletter row

**Files:**
- Create: [web/components/digest/DigestRow.tsx](../../../web/components/digest/DigestRow.tsx)

- [ ] **Step 1: Create the file**

```tsx
import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";
import type { DigestSummaryOut } from "@/lib/types/api";

function formatPeriod(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(start)} → ${fmt(end)}`;
}

function firstSentence(text: string | null): string {
  if (!text) return "Your digest";
  const m = text.match(/^[^.!?]+[.!?]/);
  return (m ? m[0] : text).trim();
}

export function DigestRow({ digest }: { digest: DigestSummaryOut }) {
  return (
    <li className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] py-6 first:border-t-0 sm:gap-6">
      <div className="col-span-12 sm:col-span-3">
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
          {formatPeriod(digest.period_start, digest.period_end)}
        </p>
        <p className="mt-2 font-mono text-xs text-[var(--ink-dim)]">
          {digest.article_count} articles
        </p>
      </div>
      <div className="col-span-12 space-y-2 sm:col-span-9">
        <h2 className="text-balance font-display text-2xl leading-snug">
          <Link
            href={`/digest?id=${digest.id}`}
            className="text-[var(--ink)] underline-offset-4 hover:underline"
          >
            {firstSentence(digest.intro)}
          </Link>
        </h2>
        {digest.top_themes.length > 0 && (
          <p className="text-sm text-[var(--ink-dim)]">
            {digest.top_themes.slice(0, 5).join(" · ")}
          </p>
        )}
        <Link
          href={`/digest?id=${digest.id}`}
          className="inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.16em] text-primary hover:underline"
        >
          Read <ArrowRightIcon className="h-3 w-3" />
        </Link>
      </div>
    </li>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/digest/DigestRow.tsx
git commit -m "feat(web): editorial DigestRow newsletter list item"
```

---

### Task 4.2: Restyle `<DigestListSkeleton />`

**Files:**
- Rewrite: [web/components/digest/DigestListSkeleton.tsx](../../../web/components/digest/DigestListSkeleton.tsx)

- [ ] **Step 1: Replace the file**

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function DigestListSkeleton() {
  return (
    <ul className="list-none p-0">
      {Array.from({ length: 4 }).map((_, i) => (
        <li
          key={i}
          className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] py-6 first:border-t-0 sm:gap-6"
        >
          <div className="col-span-12 sm:col-span-3 space-y-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
          <div className="col-span-12 sm:col-span-9 space-y-2">
            <Skeleton className="h-6 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-12" />
          </div>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/digest/DigestListSkeleton.tsx
git commit -m "style(web): editorial DigestListSkeleton"
```

---

### Task 4.3: Restyle `<EmptyState />`

**Files:**
- Rewrite: [web/components/digest/EmptyState.tsx](../../../web/components/digest/EmptyState.tsx)

- [ ] **Step 1: Replace the file**

```tsx
export function EmptyState() {
  return (
    <div className="space-y-3 border-t border-[var(--rule)] py-12 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--ink-dim)]">
        empty
      </p>
      <h3 className="font-display text-2xl">No digests yet.</h3>
      <p className="mx-auto max-w-md text-sm text-[var(--ink-dim)]">
        Daily digests are generated at 00:00 EAT. Click <strong className="text-[var(--ink)]">Remix now</strong> above for an on-demand run — about 30–60 seconds.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/digest/EmptyState.tsx
git commit -m "style(web): editorial EmptyState"
```

---

### Task 4.4: New authenticated digest list section component

**Files:**
- Create: [web/components/digest/DigestListSection.tsx](../../../web/components/digest/DigestListSection.tsx)

This is the body of the signed-in `/` page, extracted so the root page (Task 5.4) is a thin auth-branch.

- [ ] **Step 1: Create the file**

```tsx
"use client";

import { Button } from "@/components/ui/button";
import { SparklesIcon } from "lucide-react";
import { useDigestsList } from "@/lib/hooks/useDigests";
import { useRemix } from "@/lib/hooks/useRemix";
import { DigestRow } from "@/components/digest/DigestRow";
import { DigestListSkeleton } from "@/components/digest/DigestListSkeleton";
import { EmptyState } from "@/components/digest/EmptyState";

function todayLabel(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function DigestListSection() {
  const list = useDigestsList();
  const remix = useRemix();

  const digests = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="mx-auto max-w-3xl space-y-8 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--rule)] pb-6">
        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
            dispatch · {todayLabel()}
          </p>
          <h1 className="font-display text-4xl">
            Your digests<span className="text-primary">.</span>
          </h1>
        </div>
        <Button
          variant="outline"
          onClick={() => remix.mutate(24)}
          disabled={remix.isPending}
          className="font-mono text-xs uppercase tracking-[0.14em]"
        >
          <SparklesIcon className="mr-2 h-3.5 w-3.5" />
          {remix.isPending ? "Triggering…" : "Remix now"}
        </Button>
      </header>

      {list.isLoading ? (
        <DigestListSkeleton />
      ) : digests.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="list-none p-0">
          {digests.map((d) => (
            <DigestRow key={d.id} digest={d} />
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            onClick={() => list.fetchNextPage()}
            className="font-mono text-xs uppercase tracking-[0.14em]"
          >
            Load more
          </Button>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/digest/DigestListSection.tsx
git commit -m "feat(web): editorial DigestListSection (signed-in body)"
```

---

### Task 4.5: Delete obsolete `<DigestCard />`

**Files:**
- Delete: [web/components/digest/DigestCard.tsx](../../../web/components/digest/DigestCard.tsx)

- [ ] **Step 1: Confirm no remaining imports**

Run: `cd web && grep -rn "DigestCard" --include="*.tsx" --include="*.ts" .`
Expected: only `web/components/digest/DigestCard.tsx` itself appears in results. If there are imports elsewhere, fix them before deleting.

- [ ] **Step 2: Delete the file**

```bash
git rm web/components/digest/DigestCard.tsx
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(web): remove obsolete DigestCard (replaced by DigestRow)"
```

---

## Phase 5 — Public landing + route restructure

### Task 5.1: `<SampleDigestCard />` static fixture

**Files:**
- Create: [web/components/landing/SampleDigestCard.tsx](../../../web/components/landing/SampleDigestCard.tsx)

- [ ] **Step 1: Create the file**

```tsx
import { ArrowRightIcon } from "lucide-react";

export function SampleDigestCard() {
  return (
    <div
      aria-hidden
      className="relative w-full max-w-md rotate-[-2deg] rounded-lg border border-[var(--rule)] bg-[var(--surface)] p-6 shadow-[0_30px_60px_-20px_rgba(0,0,0,0.5)]"
    >
      <p className="font-mono text-[0.65rem] uppercase tracking-[0.2em] text-[var(--ink-dim)]">
        Apr 27 → Apr 28
      </p>
      <h3 className="mt-3 font-display text-xl leading-snug text-balance">
        The week MCP went mainstream — and the testing problem nobody solved.
      </h3>
      <p className="mt-2 text-sm text-[var(--ink-dim)]">
        agent reliability · MCP tooling · production testing
      </p>
      <ul className="mt-5 space-y-3 border-t border-[var(--rule)] pt-4">
        {[
          { rank: 1, title: "Persistent multi-agent conversations with OpenAI Agents SDK", score: 97 },
          { rank: 2, title: "Building AI agents we can't test or debug", score: 95 },
          { rank: 3, title: "AI agents need route, boundary, and receipt — not autonomy", score: 93 },
        ].map((a) => (
          <li key={a.rank} className="flex items-start gap-3">
            <span className="font-display text-base text-[var(--ink-dim)]">{a.rank}</span>
            <span className="flex-1 text-sm leading-snug">{a.title}</span>
            <span className="inline-flex h-5 min-w-[2rem] items-center justify-center rounded-sm bg-primary px-1.5 font-mono text-[0.7rem] tabular-nums text-primary-foreground">
              {a.score}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-5 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.16em] text-primary">
        Read <ArrowRightIcon className="h-3 w-3" />
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/landing/SampleDigestCard.tsx
git commit -m "feat(web): SampleDigestCard tilted preview for landing"
```

---

### Task 5.2: `<LandingHero />` public landing page

**Files:**
- Create: [web/components/landing/LandingHero.tsx](../../../web/components/landing/LandingHero.tsx)
- Create: [web/components/landing/__tests__/LandingHero.test.tsx](../../../web/components/landing/__tests__/LandingHero.test.tsx)

- [ ] **Step 1: Write the failing test**

Create [web/components/landing/__tests__/LandingHero.test.tsx](../../../web/components/landing/__tests__/LandingHero.test.tsx):

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LandingHero } from "@/components/landing/LandingHero";

vi.mock("@clerk/react", () => ({
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("<LandingHero />", () => {
  it("renders the hero question", () => {
    render(<LandingHero />);
    expect(
      screen.getByRole("heading", { level: 1, name: /one thing you should read today/i }),
    ).toBeInTheDocument();
  });

  it("renders both CTAs (sign-in primary + how-it-works secondary)", () => {
    render(<LandingHero />);
    expect(screen.getByRole("button", { name: /sign in to read today/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /how it works/i })).toBeInTheDocument();
  });

  it("renders the three how-it-works stages", () => {
    render(<LandingHero />);
    expect(screen.getByText(/we crawl/i)).toBeInTheDocument();
    expect(screen.getByText(/we rank/i)).toBeInTheDocument();
    expect(screen.getByText(/you read/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test — should fail**

Run: `cd web && pnpm test -- LandingHero.test`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement the component**

Create [web/components/landing/LandingHero.tsx](../../../web/components/landing/LandingHero.tsx):

```tsx
"use client";

import { SignInButton } from "@clerk/react";
import { Button } from "@/components/ui/button";
import { ArrowRightIcon } from "lucide-react";
import { SampleDigestCard } from "@/components/landing/SampleDigestCard";

const STAGES = [
  {
    n: "01",
    title: "We crawl",
    body: "RSS, YouTube, and arXiv — every hour. Roughly 80 sources tracked across AI engineering, infra, and research.",
  },
  {
    n: "02",
    title: "We rank",
    body: "An LLM scores every article 0–100 against your interests, background, and what you said you want to avoid.",
  },
  {
    n: "03",
    title: "You read",
    body: "A 5-minute morning brief. The 10 articles that actually matter to you, with a one-line reason for each.",
  },
];

export function LandingHero() {
  return (
    <div className="space-y-24 py-12">
      {/* Hero */}
      <section className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
        <div className="space-y-8 lg:col-span-7">
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--ink-dim)]">
            ai-curated daily reader
          </p>
          <h1 className="text-balance font-display text-5xl leading-[1.05] sm:text-6xl">
            What&apos;s the one thing you should read today<span className="text-primary">?</span>
          </h1>
          <p className="text-pretty text-lg leading-relaxed text-[var(--ink-dim)]">
            AI engineers and operators ship faster when they read less, not more.{" "}
            <span className="text-[var(--ink)]">digest.</span> reads ~80 sources every day and
            ranks the 10 articles you actually need — based on your background, your interests,
            and the topics you&apos;d rather skip.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <SignInButton mode="modal">
              <Button size="lg" className="font-mono text-xs uppercase tracking-[0.14em]">
                Sign in to read today&apos;s digest
                <ArrowRightIcon className="ml-2 h-4 w-4" />
              </Button>
            </SignInButton>
            <a
              href="#how"
              className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)] underline-offset-4 hover:text-[var(--ink)] hover:underline"
            >
              How it works ↓
            </a>
          </div>
        </div>
        <div className="flex justify-center lg:col-span-5 lg:justify-end">
          <SampleDigestCard />
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="space-y-10 border-t border-[var(--rule)] pt-16">
        <header className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--ink-dim)]">
            how it works
          </p>
          <h2 className="font-display text-3xl">Three stages, one quiet morning email.</h2>
        </header>
        <ol className="grid grid-cols-1 gap-8 md:grid-cols-3">
          {STAGES.map((s) => (
            <li key={s.n} className="space-y-3 border-t border-[var(--rule)] pt-4">
              <p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">{s.n}</p>
              <h3 className="font-display text-xl">{s.title}</h3>
              <p className="text-sm leading-relaxed text-[var(--ink-dim)]">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Re-run the test**

Run: `cd web && pnpm test -- LandingHero.test`
Expected: PASS — all 3 cases.

- [ ] **Step 5: Commit**

```bash
git add web/components/landing/LandingHero.tsx web/components/landing/__tests__/LandingHero.test.tsx
git commit -m "feat(web): asymmetric LandingHero for signed-out visitors"
```

---

### Task 5.3: Move private routes into a `(private)` route group

**Files:**
- Create: [web/app/(private)/layout.tsx](../../../web/app/(private)/layout.tsx) (renamed from `(authenticated)/layout.tsx`)
- Move: [web/app/(authenticated)/digest/page.tsx](../../../web/app/(authenticated)/digest/page.tsx) → [web/app/(private)/digest/page.tsx](../../../web/app/(private)/digest/page.tsx)
- Move: [web/app/(authenticated)/profile/page.tsx](../../../web/app/(authenticated)/profile/page.tsx) → [web/app/(private)/profile/page.tsx](../../../web/app/(private)/profile/page.tsx)
- Delete: [web/app/(authenticated)/page.tsx](../../../web/app/(authenticated)/page.tsx) (becomes the new root `app/page.tsx` in Task 5.4)

> **Why a rename instead of leaving the route group named `(authenticated)`?** `/` is now public, so the old name is misleading. `(private)` accurately scopes what the layout does.

- [ ] **Step 1: Create `(private)/` and move files with `git mv` (preserves history)**

```bash
cd web/app
mkdir -p '(private)'
git mv '(authenticated)/layout.tsx' '(private)/layout.tsx'
git mv '(authenticated)/digest' '(private)/digest'
git mv '(authenticated)/profile' '(private)/profile'
# The old (authenticated)/page.tsx becomes the root page in Task 5.4 — leave it for now.
cd -
```

Verify:

```bash
ls "web/app/(private)/" && ls "web/app/(authenticated)/"
```

Expected: `(private)/` has `layout.tsx`, `digest/`, `profile/`. `(authenticated)/` has `page.tsx` only.

- [ ] **Step 2: Commit the rename (no behavior change yet)**

```bash
git add web/app
git commit -m "refactor(web): rename (authenticated) route group to (private)"
```

---

### Task 5.4: Add the new public root page (auth branch)

**Files:**
- Create: [web/app/page.tsx](../../../web/app/page.tsx)
- Delete: [web/app/(authenticated)/page.tsx](../../../web/app/(authenticated)/page.tsx)
- Create: [web/app/__tests__/page.test.tsx](../../../web/app/__tests__/page.test.tsx)

- [ ] **Step 1: Write the failing branch test**

Create [web/app/__tests__/page.test.tsx](../../../web/app/__tests__/page.test.tsx):

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RootPage from "@/app/page";

const useAuthMock = vi.fn();
vi.mock("@clerk/react", () => ({
  useAuth: () => useAuthMock(),
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/hooks/useDigests", () => ({
  useDigestsList: () => ({ data: { pages: [{ items: [] }] }, isLoading: false, hasNextPage: false }),
}));
vi.mock("@/lib/hooks/useRemix", () => ({
  useRemix: () => ({ mutate: vi.fn(), isPending: false }),
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

describe("Root page (/) auth branch", () => {
  beforeEach(() => useAuthMock.mockReset());

  it("renders <LandingHero /> when not signed in", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: false });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /one thing you should read today/i }),
    ).toBeInTheDocument();
  });

  it("renders DigestListSection when signed in", () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: true });
    render(wrap(<RootPage />));
    expect(
      screen.getByRole("heading", { level: 1, name: /your digests/i }),
    ).toBeInTheDocument();
  });

  it("renders a small skeleton while Clerk is loading", () => {
    useAuthMock.mockReturnValue({ isLoaded: false, isSignedIn: false });
    render(wrap(<RootPage />));
    expect(screen.getByTestId("root-skeleton")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test — should fail**

Run: `cd web && pnpm test -- page.test`
Expected: FAIL — `app/page.tsx` doesn't exist yet.

- [ ] **Step 3: Implement the root page**

Create [web/app/page.tsx](../../../web/app/page.tsx):

```tsx
"use client";

import { useAuth } from "@clerk/react";
import { Skeleton } from "@/components/ui/skeleton";
import { LandingHero } from "@/components/landing/LandingHero";
import { DigestListSection } from "@/components/digest/DigestListSection";

export default function RootPage() {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return (
      <div data-testid="root-skeleton" className="mx-auto max-w-3xl space-y-4 py-12">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return isSignedIn ? <DigestListSection /> : <LandingHero />;
}
```

- [ ] **Step 4: Delete the old `(authenticated)/page.tsx`**

```bash
git rm "web/app/(authenticated)/page.tsx"
rmdir "web/app/(authenticated)" 2>/dev/null || true
```

- [ ] **Step 5: Re-run the test**

Run: `cd web && pnpm test -- page.test`
Expected: PASS — all 3 cases.

- [ ] **Step 6: Verify in browser**

Sign out (or use an incognito window) and visit [http://localhost:3000](http://localhost:3000) — landing page should render. Sign in and visit again — digest list should render.

- [ ] **Step 7: Commit**

```bash
git add web/app/page.tsx web/app/__tests__/page.test.tsx web/app
git commit -m "feat(web): public root page — auth-branched landing/digest list"
```

---

## Phase 6 — Profile + verification

### Task 6.1: Restyle profile page chrome (no functional changes)

**Files:**
- Modify: [web/app/(private)/profile/page.tsx](../../../web/app/(private)/profile/page.tsx)

- [ ] **Step 1: Read the file to capture current structure**

```bash
cat "web/app/(private)/profile/page.tsx"
```

- [ ] **Step 2: Update the page header and outer container**

Replace the outermost wrapper and the page heading. Locate the current `<h1>` (likely `<h1 className="text-3xl font-bold">Profile</h1>` or similar) and replace it with the editorial header below. Wrap the form in a `max-w-3xl mx-auto` container if it isn't already. Use `git diff` to confirm only the heading + container changed.

```tsx
// Inside the returned JSX, replace the outer wrapper + h1 with:
<div className="mx-auto max-w-3xl space-y-8 py-6">
  <header className="space-y-2 border-b border-[var(--rule)] pb-6">
    <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)]">
      profile
    </p>
    <h1 className="font-display text-4xl">
      Tell us what to read for you<span className="text-primary">.</span>
    </h1>
    <p className="text-sm text-[var(--ink-dim)]">
      Your interests, background, and goals shape every ranking.
    </p>
  </header>
  {/* ...existing <Form> + field groups stay here, unchanged... */}
</div>
```

The form, Zod schema, RHF wiring, and submit handler are unchanged. Only the page-level chrome moves to the editorial style.

- [ ] **Step 3: Verify in browser**

Open [http://localhost:3000/profile](http://localhost:3000/profile) (signed-in). Header should match the new style; form fields should still save successfully.

- [ ] **Step 4: Commit**

```bash
git add "web/app/(private)/profile/page.tsx"
git commit -m "style(web): editorial profile page header"
```

---

### Task 6.2: Run all checks (tests + lint + typecheck + build)

**Files:** none changed.

- [ ] **Step 1: Tests**

Run: `cd web && pnpm test`
Expected: all suites green. Existing 31 tests + new tests from Tasks 0.3, 2.1, 2.2, 5.2, 5.4.

- [ ] **Step 2: Lint**

Run: `cd web && pnpm lint`
Expected: no errors.

- [ ] **Step 3: Typecheck**

Run: `cd web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 4: Static export build**

Run: `cd web && pnpm build`
Expected: `Route ●` table prints with `/`, `/digest`, `/profile`, no `output: "export"` errors. The build artifact lands in `web/out/`.

If any step fails, stop and fix before proceeding. Don't tag.

- [ ] **Step 5: Commit any fixes (if needed)**

If lint / typecheck / build surfaced fixable issues:

```bash
git add web/
git commit -m "fix(web): redesign cleanups from full check pass"
```

If all clean, skip this step.

---

### Task 6.3: Mobile + dark/light visual pass (manual)

**Files:** none changed unless issues found.

- [ ] **Step 1: Mobile responsive check**

In Chrome DevTools, toggle device emulation to iPhone 14 (390×844). Visit `/`, `/digest?id=8`, `/profile`. Confirm:
- Landing hero stacks (headline above sample card).
- Digest list rows have date strip above title (single column).
- Article cards have rank+score gutter visible (col-span-2 on mobile).
- Profile form fields stack cleanly.

- [ ] **Step 2: Dark/light flip check**

Toggle the theme via `<ThemeToggle />`. Confirm:
- Background flips warm-white ↔ warm-slate.
- Accent stays warm-amber in both modes (slightly cooler in light per §3 spec).
- All text remains AA-readable (no `oklch(0.96)` text on `oklch(0.98)` bg).

- [ ] **Step 3: Fix anything that broke + commit if changes made**

```bash
git add web/
git commit -m "fix(web): redesign mobile/light-mode polish"
```

If clean, skip.

---

### Task 6.4: Final tag

**Files:** none changed.

- [ ] **Step 1: Confirm working tree is clean**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Tag the redesign**

```bash
git tag -a web-v0.7.0 -m "frontend redesign: editorial × terminal — landing, dark-first, YouTube preview"
```

- [ ] **Step 3: Show the tag log for the user to review**

```bash
git log web-v0.7.0 --oneline -25
```

- [ ] **Step 4: Stop**

Don't push. Wait for the user to review the diff and confirm they want it pushed before running `git push --tags origin sub-project#5`.

---

## Self-review

**Spec coverage check**

| Spec § | Implemented in |
|---|---|
| §1 Problem | n/a — narrative |
| §2 Aesthetic direction | Tasks 0.1–0.3, 1.1–1.3 (tokens + chrome express the direction) |
| §3 Design tokens | Task 0.1 |
| §4 Typography | Task 0.2 |
| §5 Brand mark | Task 1.1 |
| §6.1 Routing — `/` branch | Task 5.4 |
| §6.2 Landing hero | Tasks 5.1, 5.2 |
| §6.3 Authenticated home | Tasks 4.1–4.4 |
| §6.4 Digest detail | Tasks 3.1, 3.2 |
| §6.5 Profile (restyle only) | Task 6.1 |
| §7 YouTube preview | Tasks 2.1–2.3 |
| §8 Tailwind v4 fix | Tasks 0.1, 0.2 |
| §9 Component changes | Tasks 1.x, 4.x, 5.x (full file table covered) |
| §10 Tests | Tasks 0.3 (theme), 2.1 (youtube util), 2.2 (preview), 5.2 (landing), 5.4 (root branch); all 31 prior tests stay green per Task 6.2 |
| §11 Out of scope | n/a |
| §12 Acceptance | Verified in Tasks 6.2 + 6.3 |

No gaps.

**Placeholder scan** — no TBD/TODO. Every code block is complete and committable. No "similar to Task N" — code is repeated where needed (e.g., grid + border styling appears across DigestRow, RankedArticleCard, DigestDetailSkeleton).

**Type consistency**

- `youtubeIdFromUrl(url: string): string | null` — same signature in Task 2.1 (definition), 2.2 (consumer test ignores it but assumes it's called somewhere downstream), 2.3 (consumer in RankedArticleCard).
- `<YouTubePreview videoId: string; title: string />` — defined Task 2.2, consumed Task 2.3.
- `<DigestRow digest: DigestSummaryOut />` — defined Task 4.1, consumed Task 4.4.
- `<DigestListSection />` — defined Task 4.4, consumed Task 5.4.
- `<LandingHero />` / `<SampleDigestCard />` — defined Tasks 5.1, 5.2; consumed Task 5.4 / Task 5.2 respectively.
- Theme: `useTheme()` returns `{ theme: "light" | "dark" | "system", setTheme: (t) => void }` — same shape pre/post-rewrite.

No type drift.
