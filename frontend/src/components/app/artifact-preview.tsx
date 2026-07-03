"use client";

import { useEffect, useRef, useState } from "react";
import { Download, X } from "lucide-react";
import { getClient, type Artifact } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Report } from "@/components/app/report";
import { formatBytes } from "@/lib/utils";

type Loaded =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "markdown"; text: string }
  | { kind: "text"; text: string }
  | { kind: "image"; url: string }
  | { kind: "pdf"; url: string }
  | { kind: "unsupported" };

/**
 * Reads a delivered artifact's bytes and previews it inline — markdown rendered,
 * text/CSV/JSON as monospace, images and PDFs embedded — so a file can be opened
 * from the chat with one click instead of a download round-trip. Download stays
 * one tap away in the header.
 */
export function ArtifactPreview({
  runId,
  artifact,
  onClose,
}: {
  runId: string;
  artifact: Artifact;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<Loaded>({ kind: "loading" });

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    (async () => {
      try {
        const blob = await getClient().downloadArtifact(runId, artifact.name);
        if (cancelled) return;
        const type = blob.type || artifact.mime;
        if (type.includes("markdown") || /\.md$/i.test(artifact.name)) {
          setState({ kind: "markdown", text: await blob.text() });
        } else if (type.startsWith("text/") || type.includes("json") || type.includes("csv")) {
          setState({ kind: "text", text: await blob.text() });
        } else if (type.startsWith("image/")) {
          url = URL.createObjectURL(blob);
          setState({ kind: "image", url });
        } else if (type === "application/pdf") {
          url = URL.createObjectURL(blob);
          setState({ kind: "pdf", url });
        } else {
          setState({ kind: "unsupported" });
        }
      } catch {
        if (!cancelled) setState({ kind: "error" });
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [runId, artifact.name, artifact.mime]);

  function save() {
    getClient()
      .downloadArtifact(runId, artifact.name)
      .then((blob) => {
        const u = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = u;
        a.download = artifact.name;
        a.click();
        URL.revokeObjectURL(u);
      });
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="m-auto h-[85dvh] w-[calc(100vw-2rem)] max-w-3xl rounded-lg border border-border bg-surface-raised p-0 text-foreground shadow-2xl backdrop:bg-black/55 backdrop:backdrop-blur-[2px] open:animate-fade-up"
    >
      <div className="flex h-full flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{artifact.name}</p>
            <p className="text-[12px] text-faint tabular">
              {artifact.mime} · {formatBytes(artifact.size)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="outline" size="sm" onClick={save}>
              <Download className="size-4" aria-hidden /> Download
            </Button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close preview"
              className="flex size-9 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-auto">
          {state.kind === "loading" && (
            <div className="p-6">
              <Skeleton className="h-[60dvh]" />
            </div>
          )}
          {state.kind === "error" && (
            <p className="p-6 text-sm text-muted-foreground">
              Couldn&apos;t load this file for preview. Try downloading it instead.
            </p>
          )}
          {state.kind === "markdown" && (
            <div className="px-5 py-5 sm:px-7">
              <Report markdown={state.text} />
            </div>
          )}
          {state.kind === "text" && (
            <pre className="whitespace-pre-wrap break-words p-5 font-mono text-[13px] leading-relaxed text-muted-foreground">
              {state.text}
            </pre>
          )}
          {state.kind === "image" && (
            <div className="flex h-full items-center justify-center p-5">
              {/* object-URL blob — next/image can't size these; a plain img is right */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={state.url} alt={artifact.name} className="max-h-full max-w-full rounded" />
            </div>
          )}
          {state.kind === "pdf" && (
            <iframe src={state.url} title={artifact.name} className="size-full" />
          )}
          {state.kind === "unsupported" && (
            <p className="p-6 text-sm text-muted-foreground">
              No inline preview for this file type — download it to open.
            </p>
          )}
        </div>
      </div>
    </dialog>
  );
}
