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
