"use client";

import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/input";
import { FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";

export function ReadingTimeFieldGroup() {
  const { control } = useFormContext();
  return (
    <fieldset className="space-y-4">
      <legend className="font-semibold">Reading time</legend>
      <FormField
        control={control}
        name="reading_time.daily_limit"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Daily limit</FormLabel>
            <Input {...field} placeholder="20 minutes" />
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="reading_time.preferred_article_count"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Preferred article count</FormLabel>
            <Input {...field} placeholder="10" />
            <FormMessage />
          </FormItem>
        )}
      />
    </fieldset>
  );
}
