"use client";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { OnboardingGate } from "@/components/auth/OnboardingGate";

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <OnboardingGate>{children}</OnboardingGate>
    </RequireAuth>
  );
}
