"use client";

import { forwardRef, useId, useState, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

const fieldBase =
  // 16px on mobile — anything smaller makes iOS Safari zoom the page on focus
  "w-full rounded-md border border-border-strong bg-surface-raised px-3.5 text-base sm:text-[15px] text-foreground " +
  "placeholder:text-faint transition-colors duration-150 " +
  "hover:border-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:focus:ring-destructive/25";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, label, error, hint, id: idProp, type, required, ...props },
  ref,
) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const [show, setShow] = useState(false);
  const isPassword = type === "password";

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-[13px] font-medium text-muted-foreground">
          {label}
          {/* tucked to the label, quiet — error red is for errors, and a
              two-field form doesn't need its labels shouting "required" */}
          {required && <span className="text-faint" aria-hidden>*</span>}
        </label>
      )}
      <div className="relative">
        <input
          ref={ref}
          id={id}
          type={isPassword && show ? "text" : type}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className={cn(fieldBase, "h-11", isPassword && "pr-11", className)}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? "Hide password" : "Show password"}
            className="absolute right-1 top-1/2 flex size-9 -translate-y-1/2 cursor-pointer items-center justify-center rounded-sm text-faint hover:text-foreground"
          >
            {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </div>
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-[13px] text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[13px] text-faint">
          {hint}
        </p>
      ) : null}
    </div>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ className, label, error, id: idProp, ...props }, ref) {
    const autoId = useId();
    const id = idProp ?? autoId;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-[13px] font-medium text-muted-foreground">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(fieldBase, "min-h-24 py-3 leading-relaxed", className)}
          {...props}
        />
        {error && (
          <p id={`${id}-error`} role="alert" className="text-[13px] text-destructive">
            {error}
          </p>
        )}
      </div>
    );
  },
);
