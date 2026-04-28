# Frontend Redesign — Editorial × Terminal

**Status:** approved (2026-04-28)
**Supersedes:** visual / structural sections of [2026-04-28-frontend-design.md](./2026-04-28-frontend-design.md). Functional contract (auth, hooks, data flow, static export, supply chain, CI/CD) is unchanged.
**Why this exists:** the v1 implementation shipped working but with broken Tailwind v4 setup, no public landing surface, and no media-aware article rendering. This spec captures the redesign.

---

## 1. Problem

Three issues motivate this rewrite:

1. **Broken Tailwind v4 setup.** [web/app/globals.css](../../../web/app/globals.css) mixes v3 directives (`@tailwind base/components/utilities`) with v4 syntax (`@theme inline`, `@custom-variant`) and ships two parallel CSS variable systems (HSL + OKLCH). Result: tokens like `bg-card` and `bg-secondary` don't resolve cleanly, badges with `rounded-4xl` overflow text, cards lose borders. Visible in the user's screenshots of [/](http://localhost:3000) and [/digest?id=8](http://localhost:3000/digest?id=8).
2. **No conversion surface for signed-out visitors.** Visiting [/](http://localhost:3000) immediately bounces unauthenticated users to Clerk's hosted sign-in. There's no page that explains what `digest` is or why someone would sign up.
3. **No media-aware rendering.** When a `RankedArticle.url` points at YouTube, it renders as a raw underlined link. Video sources should embed inline with an "open in YouTube" escape hatch.

## 2. Aesthetic direction

**Editorial × Terminal** — a curated AI-briefing reader, not a SaaS dashboard. Restrained, opinionated, monospace metadata, oversized serif headlines, asymmetric layout, single warm accent on dark.

Explicitly **not**:
- Indigo/violet gradients on white (the AI-cliché trap the frontend-design skill warns against).
- shadcn-stock look with rounded cards on grey backgrounds.
- Generic SaaS pricing-page hero with three feature cards in a row.

## 3. Design tokens

Replaces the entire `:root` / `.dark` block in [globals.css](../../../web/app/globals.css). All values OKLCH, single source of truth, no HSL fallback.

```css
:root {
  /* Dark = default. Light = inverse, exposed via .light class on <html>. */
  --bg:          oklch(0.16 0.012 245);   /* warm slate, never #000 */
  --surface:    oklch(0.20 0.014 245);   /* cards */
  --surface-2:  oklch(0.23 0.014 245);   /* hover, selected */
  --ink:         oklch(0.96 0.018 80);    /* ivory body text */
  --ink-dim:    oklch(0.66 0.012 80);    /* metadata, captions */
  --rule:        oklch(0.30 0.012 245);   /* hairline borders */
  --accent:      oklch(0.78 0.16 65);     /* warm amber — CTA + score */
  --accent-ink: oklch(0.18 0.020 65);    /* text on accent */
  --danger:     oklch(0.65 0.20 25);     /* destructive */
  --radius:     0.5rem;
}

.light {
  --bg:          oklch(0.98 0.006 80);
  --surface:    oklch(0.96 0.008 80);
  --surface-2:  oklch(0.93 0.010 80);
  --ink:         oklch(0.18 0.012 245);
  --ink-dim:    oklch(0.42 0.010 245);
  --rule:        oklch(0.86 0.010 245);
  --accent:      oklch(0.62 0.18 65);
  --accent-ink: oklch(0.98 0.006 80);
  --danger:     oklch(0.55 0.20 25);
}
```

Semantic shadcn token aliasing in `@theme inline`:

| shadcn token | Maps to |
|---|---|
| `--color-background` | `var(--bg)` |
| `--color-foreground` | `var(--ink)` |
| `--color-card` | `var(--surface)` |
| `--color-card-foreground` | `var(--ink)` |
| `--color-muted` | `var(--surface-2)` |
| `--color-muted-foreground` | `var(--ink-dim)` |
| `--color-primary` | `var(--accent)` |
| `--color-primary-foreground` | `var(--accent-ink)` |
| `--color-border` | `var(--rule)` |
| `--color-destructive` | `var(--danger)` |
| `--color-ring` | `var(--accent)` |

shadcn `<Card>` / `<Button>` / `<Badge>` keep working unchanged.

## 4. Typography

Three fonts loaded via `next/font/google` to keep static-export compatibility:

| Role | Font | Where |
|---|---|---|
| Display | [Fraunces](https://fonts.google.com/specimen/Fraunces) (variable, opsz 11–144) | h1, hero, digest titles |
| Body | [Geist](https://vercel.com/font) Sans | everything else |
| Mono | [Geist Mono](https://vercel.com/font) | dates, scores, ranks, IDs, "Apr 27 → Apr 28" |

`@theme inline` exposes them as `--font-display`, `--font-sans`, `--font-mono` — all literal fontstack strings, never `var(--font-sans)` self-references (would break per the shadcn skill warning).

`<html>` carries the variable classNames (`fraunces.variable + geist.variable + geistMono.variable`), `<body>` uses `font-sans` by default.

## 5. Brand mark

Header lockup: **`digest.`** — Fraunces 600, the period in `--accent`. No icon, no logo. Replaces the current `<span className="text-lg">digest</span>` raw text.

## 6. Page architecture

### 6.1 `/` — landing for signed-out, digest list for signed-in

The decision is made client-side on `(authenticated)/page.tsx` using `useAuth().isSignedIn`. No middleware (incompatible with static export).

**Signed-out:** full landing page (`<LandingHero />`).
**Signed-in:** editorial header band + digest list.

### 6.2 Landing (`<LandingHero />`)

Single screen, asymmetric grid (12-col on desktop, stacked on mobile):

- **Left 7/12** — oversized Fraunces headline:
  > "What's the one thing you should read today?"

  Sub-headline (Geist 18px, `--ink-dim`):
  > "AI engineers and operators ship faster when they read less, not more. `digest.` reads ~80 sources daily and ranks the 10 you actually need."

  Two CTAs: filled amber **"Sign in to read today's digest"** + outline **"How it works"** (anchor scroll to a `#how` section).

- **Right 5/12** — a tilted (`rotate(-2deg)`), partially-clipped, **live-rendered** sample digest card. Static fixture data, no API call. Shows a Fraunces title, mono date strip, two themes as comma-separated text, an amber score chip on one article. Visually conveys the product without screenshots.

- **Below the fold** — `#how` section: 3 stages laid out as a horizontal timeline with hairline rules:
  1. *We crawl* — RSS + YouTube + arXiv, every hour.
  2. *We rank* — your profile + LLM scoring against your interests.
  3. *You read* — a 5-minute morning brief, plus optional email.

- **Footer ribbon** — mono, hairline border above:
  `daily · ai-curated · ranked 0–100 · ~5 min read`

No "Free trial" / "No credit card required" / "Trusted by X" dross. The product speaks for itself.

### 6.3 Authenticated home (signed-in `/`)

Editorial-newsletter layout, **not** a card grid:

- **Header band** (replaces current `<h1>Your digests</h1>` + button row):
  - Mono caption: `dispatch · {today's date}`
  - Fraunces h1: `Your digests.`
  - Right side: `Remix now` outline button with sparkles glyph + small `last refreshed {relativeTime}` mono caption underneath.
- **List** — single column, `max-w-2xl`, generous gutter:
  - Each digest is a horizontal row with hairline divider:
    - Mono left rail (col-span-2): period as `Apr 27 → Apr 28` (mono, dim).
    - Body (col-span-10): Fraunces 22px title (the `digest.intro` first sentence, fallback to "Your digest"), Geist body with themes as `·`-separated text, then `→ Read` link in amber.
- **Pagination** — current `Load more` button kept but restyled as a centered ghost button.

Empty / skeleton states unchanged in behavior, restyled to match.

### 6.4 Digest detail (`/digest?id=N`)

Editorial article layout:

- **Banner**:
  - Mono caption: `Apr 26, 2026 — Apr 27, 2026`
  - Fraunces 5xl: `Your digest.`
  - Themes as a single line of `·`-separated Geist 14px text in `--ink-dim`. **Kills the broken-pill bug entirely** — they're not pills anymore.
- **Intro** — Geist 18px, max 65ch.
- **Article list** — each article is a `<Card>`:
  - Left gutter (col-span-1): rank number Fraunces 4xl + amber score chip below it (mono, monospace, e.g. `97`).
  - Body (col-span-11): Fraunces 24px title (anchor to `article.url`, opens in new tab), Geist 16px summary, then "Why this article" as a pulled quote with 2px amber `border-l` and Geist italic.
  - **YouTube preview card** when applicable (see §7).

### 6.5 Profile

No structural changes. Re-styles only — Fraunces page title, Geist labels and inputs, amber save button. Forms keep the existing RHF + Zod logic.

## 7. YouTube preview

### 7.1 Detection

`web/lib/utils/youtube.ts`:

```ts
export function youtubeIdFromUrl(url: string): string | null {
  // Matches youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID, youtube.com/embed/ID.
  // Returns the 11-char video ID or null.
}
```

Pure function, fully unit-tested.

### 7.2 Rendering

`web/components/digest/YouTubePreview.tsx`:

- Renders a 16:9 `<iframe src="https://www.youtube-nocookie.com/embed/{id}" loading="lazy" allow="accelerometer; encrypted-media; picture-in-picture" allowfullscreen>`.
- Below: `Open on YouTube ↗` link (mono, dim, opens `https://youtu.be/{id}` in a new tab).
- The `youtube-nocookie.com` host is the privacy-enhanced embed — no third-party cookies until the user clicks play. No GDPR banner needed.

### 7.3 Integration

`<RankedArticleCard>` checks `youtubeIdFromUrl(article.url)`. If non-null, renders `<YouTubePreview videoId={...} />` *above* the title. The title still anchors to the original `article.url` (which IS the YouTube watch link).

## 8. Tailwind v4 fix

`globals.css` rewrite:

```css
@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:is(:not(.light) *));

@theme inline {
  --color-background:  var(--bg);
  --color-foreground:  var(--ink);
  /* ...all aliases per §3... */

  --font-display: "Fraunces Variable", "Fraunces", ui-serif, Georgia, serif;
  --font-sans:    "Geist", "Geist Fallback", ui-sans-serif, system-ui, sans-serif;
  --font-mono:    "Geist Mono", "Geist Mono Fallback", ui-monospace, "JetBrains Mono", monospace;

  --radius-sm: calc(var(--radius) * 0.6);
  --radius-md: calc(var(--radius) * 0.8);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) * 1.4);
}

:root  { /* dark tokens per §3 */ }
.light { /* light tokens per §3 */ }

@layer base {
  *  { @apply border-border outline-ring/50; }
  body { @apply bg-background text-foreground antialiased; font-feature-settings: "ss01", "cv11"; }
  h1, h2, h3 { font-family: var(--font-display); letter-spacing: -0.02em; }
}
```

The default-theme inversion (`dark` is no-class, `light` is `.light` class) flips the existing FOUC-prevention script in [layout.tsx](../../../web/app/layout.tsx) — it must add `.light` instead of `.dark`. The existing `ThemeProvider` is updated symmetrically.

## 9. Component changes

| File | Change |
|---|---|
| [web/app/layout.tsx](../../../web/app/layout.tsx) | Load Fraunces + Geist + Geist Mono via `next/font/google`. Move font className from `<body>` to `<html>`. Flip FOUC script to add `.light` instead of `.dark`. |
| [web/app/globals.css](../../../web/app/globals.css) | Full rewrite per §8. |
| [web/lib/theme.tsx](../../../web/lib/theme.tsx) | Default theme `dark`. Toggle adds/removes `.light` class. Symmetric to existing API — no consumer changes. |
| [web/components/layout/Header.tsx](../../../web/components/layout/Header.tsx) | Replace `<span>digest</span>` with `<Logo />` (Fraunces + accent period). |
| [web/components/layout/Footer.tsx](../../../web/components/layout/Footer.tsx) | Mono ribbon. |
| [web/components/landing/LandingHero.tsx](../../../web/components/landing/LandingHero.tsx) | New. Public landing page §6.2. |
| [web/components/landing/SampleDigestCard.tsx](../../../web/components/landing/SampleDigestCard.tsx) | New. Static fixture digest preview, tilted -2deg. |
| [web/components/digest/DigestRow.tsx](../../../web/components/digest/DigestRow.tsx) | New. Editorial row replacing `DigestCard.tsx` on the home list. |
| [web/components/digest/DigestCard.tsx](../../../web/components/digest/DigestCard.tsx) | **Delete** (replaced by DigestRow). |
| [web/components/digest/RankedArticleCard.tsx](../../../web/components/digest/RankedArticleCard.tsx) | Restyle: gutter rank + score chip, pulled-quote "why" block, YouTube preview integration. |
| [web/components/digest/YouTubePreview.tsx](../../../web/components/digest/YouTubePreview.tsx) | New. §7. |
| [web/lib/utils/youtube.ts](../../../web/lib/utils/youtube.ts) | New. §7.1. |
| [web/app/(authenticated)/page.tsx](../../../web/app/(authenticated)/page.tsx) | Branch on `isSignedIn`: `<LandingHero />` vs editorial digest list. |
| [web/components/digest/EmptyState.tsx](../../../web/components/digest/EmptyState.tsx) | Restyle. |

The auth route group `(authenticated)/layout.tsx` and its `<RequireAuth>` move out: `/` is now public. `/digest` and `/profile` keep `<RequireAuth>` via a new route group `(private)`.

## 10. Tests

- **Unit** — `youtubeIdFromUrl` covers `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/embed/`, query string with extra params, plain non-YouTube URLs.
- **Component** — `<YouTubePreview>` renders an iframe with the right `src` and an "Open on YouTube" link. `<LandingHero>` renders both CTAs and the "How it works" section.
- **Integration** — `(authenticated)/page.tsx` renders `<LandingHero />` when `isSignedIn === false` and the editorial digest list when `true`. Existing tests for `useDigests` polling stay green.
- **Accessibility** — manual keyboard + screen-reader smoke pass on the landing hero and digest detail. No new dep (avoids supply-chain vet for the redesign).

All 31 existing tests must stay green.

## 11. Out of scope

- Light mode polish (functional, but only briefly tested).
- Animations beyond CSS hover transitions and a single staggered fade-in on the landing hero.
- Custom logo / brand SVG (the typographic mark is the brand).
- E2E (deferred per the parent spec).

## 12. Acceptance

- [`/` signed-out] Renders landing page with both CTAs visible above the fold.
- [`/` signed-in] Renders editorial header + digest list with Fraunces titles, mono dates, hairline dividers.
- [`/digest?id=N`] Shows banner, themes-as-text (no broken pills), ranked articles in cards with score chip in left gutter.
- [`/digest?id=N` with a YouTube article] Shows the embedded preview above the title with an "Open on YouTube ↗" link.
- [Mobile] Landing single-column, digest detail readable at 375px.
- [Theme] Toggle flips between dark (default) and light without FOUC.
- [Tests] `pnpm test` green; `pnpm typecheck` green; `pnpm lint` green.
- [Build] `pnpm build` produces a static export with no `output: "export"` errors.
