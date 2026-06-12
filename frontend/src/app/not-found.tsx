import { Mark } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-5 text-center">
      <Mark className="size-12 text-primary opacity-60" />
      <h1 className="display mt-6 text-[3rem] leading-[1.0]">
        This branch doesn&apos;t exist
      </h1>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
        The page you&apos;re looking for was never grown — or it was pruned.
        The archive itself is intact.
      </p>
      <div className="mt-8 flex gap-3">
        <ButtonLink href="/" variant="outline">
          Home
        </ButtonLink>
        <ButtonLink href="/app">Workspace</ButtonLink>
      </div>
    </div>
  );
}
