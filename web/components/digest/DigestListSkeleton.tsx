import { Skeleton } from "@/components/ui/skeleton";

export function DigestListSkeleton() {
  return (
    <ul className="list-none p-0">
      {Array.from({ length: 4 }).map((_, i) => (
        <li
          key={i}
          className="grid grid-cols-12 gap-4 border-t border-[var(--rule)] py-6 first:border-t-0 sm:gap-6"
        >
          <div className="col-span-12 sm:col-span-3 space-y-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
          <div className="col-span-12 sm:col-span-9 space-y-2">
            <Skeleton className="h-6 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-12" />
          </div>
        </li>
      ))}
    </ul>
  );
}
