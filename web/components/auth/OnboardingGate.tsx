"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useMe } from "@/lib/hooks/useMe";

/**
 * Redirects signed-in users with `profile_completed_at === null` to
 * `/profile?onboarding=1` so they fill in interests/background before
 * landing on an inevitably-empty digest list. Renders `children` until the
 * redirect runs (one frame, invisible).
 *
 * No-op for signed-out users — `useMe()` returns no data without a JWT, so
 * the effect's guard short-circuits. Safe to wrap any authenticated branch.
 */
export function OnboardingGate({ children }: { children: React.ReactNode }) {
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
