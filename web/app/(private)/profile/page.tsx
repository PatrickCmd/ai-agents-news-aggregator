"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useForm, FormProvider, type SubmitHandler } from "react-hook-form";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const form = useForm<any>({
    resolver: standardSchemaResolver(UserProfileSchema),
    defaultValues: me?.profile ?? EMPTY_PROFILE,
  });

  // When /me loads after the form mounts, reset the form with the loaded values.
  useEffect(() => {
    if (me?.profile) form.reset(me.profile);
  }, [me, form]);

  // After Zod validation all arrays are populated; cast to UserProfile is safe.
  const onSubmit: SubmitHandler<UserProfile> = (data) => update.mutate(data);

  return (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      {onboarding && <OnboardingBanner />}

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

      <FormProvider {...form}>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <BackgroundFieldArray />
            <InterestsFieldGroup />
            <PreferencesFieldGroup />
            <GoalsFieldArray />
            <ReadingTimeFieldGroup />

            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button
                type="button"
                variant="outline"
                onClick={() => form.reset(me?.profile ?? EMPTY_PROFILE)}
              >
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
