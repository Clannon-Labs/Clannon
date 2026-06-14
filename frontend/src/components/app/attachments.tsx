"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Paperclip, X } from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { MAX_FILES, isAudioOrVideo, rejectInputFile } from "@/lib/uploads";

/**
 * Shared file-attachment state for the composers: a validated `File[]` with a
 * picker plus flicker-free drag-and-drop, behind one hook so every composer
 * enforces the exact same limits. Spread `dropZoneProps` onto the drop target,
 * wire `handlePicked` to a hidden file input (the consumer keeps that input's
 * ref so it can open the picker), and render the files with <AttachmentChips>.
 */
export function useFileAttachments() {
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragDepth = useRef(0); // avoids flicker as the drag crosses child nodes

  function addFiles(picked: File[]) {
    setError(null);
    const next = [...files];
    for (const f of picked) {
      if (next.length >= MAX_FILES) {
        setError(`Up to ${MAX_FILES} files per run.`);
        break;
      }
      if (next.some((e) => e.name === f.name && e.size === f.size)) continue; // dedupe
      const reason = rejectInputFile(f);
      if (reason) {
        setError(reason);
        continue;
      }
      next.push(f);
    }
    setFiles(next);
  }

  function handlePicked(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow re-picking the same file
    if (picked.length) addFiles(picked);
  }

  const dropZoneProps = {
    onDragEnter: (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragDepth.current += 1;
      setDragOver(true);
    },
    onDragOver: (e: DragEvent<HTMLDivElement>) => e.preventDefault(), // allow drop
    onDragLeave: (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragDepth.current -= 1;
      if (dragDepth.current <= 0) {
        dragDepth.current = 0;
        setDragOver(false);
      }
    },
    onDrop: (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragDepth.current = 0;
      setDragOver(false);
      const dropped = Array.from(e.dataTransfer.files);
      if (dropped.length) addFiles(dropped);
    },
  };

  return {
    files,
    error,
    dragOver,
    hasHeavyMedia: files.some(isAudioOrVideo),
    addFiles,
    removeFile: (index: number) => setFiles((prev) => prev.filter((_, i) => i !== index)),
    clear: () => {
      setFiles([]);
      setError(null);
    },
    handlePicked,
    dropZoneProps,
  };
}

/** Removable chips for the currently attached files. */
export function AttachmentChips({
  files,
  onRemove,
}: {
  files: File[];
  onRemove: (index: number) => void;
}) {
  if (files.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2 px-4 pb-1">
      {files.map((f, i) => (
        <li
          key={`${f.name}-${f.size}-${i}`}
          className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-muted-foreground"
        >
          <Paperclip className="size-3 shrink-0 text-faint" aria-hidden />
          <span className="truncate">{f.name}</span>
          <span className="shrink-0 text-faint tabular">{formatBytes(f.size)}</span>
          <button
            type="button"
            onClick={() => onRemove(i)}
            aria-label={`Remove ${f.name}`}
            className="flex size-5 shrink-0 cursor-pointer items-center justify-center rounded text-faint hover:text-destructive"
          >
            <X className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The "drop files here" overlay shown while dragging over a composer. */
export function DropOverlay({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-primary-soft/80 backdrop-blur-sm">
      <span className="flex items-center gap-2 text-sm font-medium text-primary">
        <Paperclip className="size-4" aria-hidden /> Drop files to attach
      </span>
    </div>
  );
}

/** Quiet note shown when an attached clip is heavy enough to risk the model's inline limit. */
export function HeavyMediaNote({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <p className="px-4 pb-1 text-[12px] text-faint">
      A very large audio or video can exceed the model&apos;s inline limit — that one run fails gracefully if so.
    </p>
  );
}
