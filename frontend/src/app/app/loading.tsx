import { Skeleton } from "@/components/ui/skeleton";

export default function WorkspaceLoading() {
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
