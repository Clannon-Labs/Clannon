import { Skeleton } from "@/components/ui/skeleton";

export default function RunsLoading() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-[60vh]" />
    </div>
  );
}
