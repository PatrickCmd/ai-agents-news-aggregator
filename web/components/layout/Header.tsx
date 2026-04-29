"use client";

import Link from "next/link";
import { useAuth, UserButton } from "@clerk/react";
import { Logo } from "@/components/layout/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

export function Header() {
  const { isSignedIn } = useAuth();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-[var(--rule)] bg-[var(--bg)] bg-[color-mix(in_oklch,var(--bg)_88%,transparent)] backdrop-blur supports-[backdrop-filter]:bg-[color-mix(in_oklch,var(--bg)_70%,transparent)]">
      <div className="container flex h-16 items-center justify-between">
        <Logo />
        <div className="flex items-center gap-3 sm:gap-4">
          {isSignedIn && (
            <Link
              href="/profile"
              className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--ink-dim)] underline-offset-4 transition-colors hover:text-[var(--ink)] hover:underline"
            >
              Profile
            </Link>
          )}
          <ThemeToggle />
          <UserButton appearance={{ elements: { avatarBox: "h-8 w-8" } }} />
        </div>
      </div>
    </header>
  );
}
