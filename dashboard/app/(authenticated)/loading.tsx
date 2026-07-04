import { Skeleton } from "@/components/ui/skeleton";

/**
 * Loading boundary for the authenticated route group.
 *
 * Shown by Next.js while server components / data fetches in this segment are
 * in flight, replacing a blank screen with a skeleton shell that mirrors the
 * authenticated layout: a left sidebar column and a main content area.
 */
export default function Loading() {
  return (
    <div className="flex min-h-screen">
      <aside className="w-64 border-r p-4">
        <Skeleton className="h-8 w-full" />
        <div className="mt-6 space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </aside>
      <main className="flex-1 p-6 md:p-8">
        <Skeleton className="h-8 w-48" />
        <div className="mt-6 grid gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </main>
    </div>
  );
}
