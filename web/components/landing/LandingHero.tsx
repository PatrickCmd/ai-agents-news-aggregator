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
