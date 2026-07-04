"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * Renders pipeline-delivered markdown. react-markdown never injects
 * raw HTML (no rehype-raw here, deliberately) and sanitizes URL
 * protocols by default. Images are dropped — reports are text + tables.
 */
export function Report({
  markdown,
  streaming,
  ornate,
  className,
}: {
  markdown: string;
  streaming?: boolean;
  /** Drop-initial on the opening paragraph — set once delivery is final. */
  ornate?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "report-prose",
        ornate && "report-ornate",
        // the caret rides the END of the last rendered line (a ::after on the
        // last block), never an orphan block of its own
        streaming && "stream-caret",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: () => null,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border bg-muted px-3.5 py-2 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/50 px-3.5 py-2 align-top text-muted-foreground">
              {children}
            </td>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>

    </div>
  );
}
