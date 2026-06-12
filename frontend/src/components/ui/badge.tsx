import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "primary" | "memory" | "destructive" | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary-soft text-primary",
  memory: "bg-memory-soft text-memory",
  destructive: "bg-destructive-soft text-destructive",
  outline: "border border-border-strong text-muted-foreground",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "tag-label inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
