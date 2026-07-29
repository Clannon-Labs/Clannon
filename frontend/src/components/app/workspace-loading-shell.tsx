import { Mark } from "@/components/brand/logo";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Data-shaped workspace content. Dimensions mirror the resolved new-chat page,
 * so backend latency changes texture instead of moving the whole interface.
 */
export function WorkspacePageLoading() {
  return (
    <div className="mx-auto flex min-h-[calc(100dvh-7rem)] max-w-3xl flex-col md:min-h-[calc(100dvh-4rem)]">
      <div className="flex flex-1 flex-col">
        <div className="flex flex-col items-center pt-[9vh] sm:pt-[10vh]">
          <Skeleton className="h-10 w-56 sm:h-12 sm:w-72" />
          <Skeleton className="mt-4 h-4 w-72 sm:w-80" />
          <Skeleton className="mt-2 h-4 w-52 sm:w-64" />
        </div>
        <div className="mt-10 grid gap-2.5 sm:grid-cols-3 sm:gap-3">
          <Skeleton className="h-[72px] rounded-2xl sm:h-24 sm:rounded-xl" />
          <Skeleton className="h-[72px] rounded-2xl sm:h-24 sm:rounded-xl" />
          <Skeleton className="h-[72px] rounded-2xl sm:h-24 sm:rounded-xl" />
        </div>
        <Skeleton className="mt-12 h-24 rounded-lg" />
      </div>
      <div className="sticky bottom-0 z-30 border-t border-border bg-background pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3">
        <Skeleton className="h-[68px] w-full rounded-xl" />
      </div>
    </div>
  );
}

/**
 * First-response shell for /app. Passed from the server layout into the client
 * auth gate as rendered children: real geometry arrives in HTML, while no
 * sidebar interactions or account data join the initial client bundle.
 */
export function WorkspaceLoadingShell() {
  return (
    <div role="status" aria-label="Loading your workspace" className="min-h-dvh bg-background">
      <aside
        aria-hidden
        className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-border bg-stage md:flex"
      >
        <div className="flex h-16 items-center gap-2.5 px-5">
          <Mark className="size-6" />
          <span className="font-display text-lg font-medium tracking-tight">Clannon</span>
        </div>
        <div className="space-y-3 px-3">
          <Skeleton className="h-14 rounded-xl" />
          <Skeleton className="h-9 rounded-md" />
          <Skeleton className="h-9 rounded-md" />
          <Skeleton className="h-9 rounded-md" />
        </div>
        <div className="mt-8 space-y-2 px-5">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-8" />
          <Skeleton className="h-8 w-4/5" />
          <Skeleton className="h-8 w-3/5" />
        </div>
        <div className="mt-auto space-y-3 border-t border-border p-4">
          <Skeleton className="h-16 rounded-lg" />
          <Skeleton className="h-10 rounded-md" />
        </div>
      </aside>

      <header
        aria-hidden
        className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-4 md:hidden"
      >
        <div className="flex items-center gap-2.5">
          <Skeleton className="size-8" />
          <Mark className="size-5" />
          <span className="font-display text-base font-medium">Clannon</span>
        </div>
        <div className="flex gap-2">
          <Skeleton className="size-8" />
          <Skeleton className="size-8" />
        </div>
      </header>

      <main className="px-4 pb-10 pt-20 sm:px-6 md:ml-60 md:pt-8 lg:px-10">
        <WorkspacePageLoading />
      </main>
    </div>
  );
}
