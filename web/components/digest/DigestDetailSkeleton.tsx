import { Skeleton } from "@/components/ui/skeleton";

export function DigestDetailSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      <div className="space-y-3">
        <Skeleton className="h-3 w-48" />
        <Skeleton className="h-12 w-3/4" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <Skeleton className="h-20 w-full" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] pt-6">
          <div className="col-span-2 sm:col-span-1 space-y-2">
            <Skeleton className="h-7 w-7" />
            <Skeleton className="h-5 w-9" />
          </div>
          <div className="col-span-10 sm:col-span-11 space-y-2">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>
      ))}
    </div>
  );
}
