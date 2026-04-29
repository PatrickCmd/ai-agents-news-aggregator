"use client";

import Link from "next/link";
import { useAuth, useUser, UserButton } from "@clerk/react";
import { Logo } from "@/components/layout/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

function displayName(user: ReturnType<typeof useUser>["user"]): string {
  if (!user) return "";
  return (
    user.firstName ||
    user.username ||
    user.primaryEmailAddress?.emailAddress.split("@")[0] ||
    ""
  );
}

export function Header() {
  const { isSignedIn } = useAuth();
  const { user } = useUser();
  const greeting = displayName(user).toLowerCase();

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
          {isSignedIn && greeting && (
            <span
              className="hidden font-mono text-xs text-[var(--ink-dim)] sm:inline-block"
              aria-label={`Signed in as ${greeting}`}
            >
              hi, {greeting}
            </span>
          )}
          <UserButton appearance={{ elements: { avatarBox: "h-8 w-8" } }} />
        </div>
      </div>
    </header>
  );
}
