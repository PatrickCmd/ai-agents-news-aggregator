"use client";

import { useAuth } from "@clerk/react";
import { Skeleton } from "@/components/ui/skeleton";
import { LandingHero } from "@/components/landing/LandingHero";
import { DigestListSection } from "@/components/digest/DigestListSection";
import { OnboardingGate } from "@/components/auth/OnboardingGate";

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

  // Signed-in: gate on profile completion before showing digests. New users
  // (profile_completed_at === null) get redirected to /profile?onboarding=1.
  // Signed-out: public landing.
  return isSignedIn ? (
    <OnboardingGate>
      <DigestListSection />
    </OnboardingGate>
  ) : (
    <LandingHero />
  );
}
