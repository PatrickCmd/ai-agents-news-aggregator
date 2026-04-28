import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SparklesIcon } from "lucide-react";

export function OnboardingBanner() {
  return (
    <Alert>
      <SparklesIcon className="h-4 w-4" />
      <AlertTitle>Welcome!</AlertTitle>
      <AlertDescription>
        Complete your profile to start receiving daily digests at 00:00 EAT, or trigger an
        on-demand remix any time after.
      </AlertDescription>
    </Alert>
  );
}
