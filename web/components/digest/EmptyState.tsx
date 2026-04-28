import { CalendarIcon } from "lucide-react";

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
      <CalendarIcon className="h-12 w-12 mb-4 opacity-50" />
      <h3 className="font-medium text-foreground">No digests yet</h3>
      <p className="mt-1 text-sm max-w-sm">
        Daily digests are generated at 00:00 EAT. Click &quot;Remix now&quot; above for an on-demand run.
      </p>
    </div>
  );
}
