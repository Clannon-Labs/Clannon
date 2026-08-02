"use client";

/**
 * Editorial motion vocabulary (Motion v12).
 *
 * The whole frontend speaks four gestures, no more — restraint is the point:
 *   <TypeSet>   a line of type that sets itself (rises out of its own baseline)
 *   <Stagger>   a column whose children arrive one after another
 *   <Reveal>    a block that rises into place on scroll
 *   <Rule>      a hairline that draws itself left-to-right
 *
 * Every gesture collapses to a static, instant render under
 * prefers-reduced-motion (honored globally by <MotionConfig reducedMotion="user">
 * in providers, and per-component here via `initial={false}`).
 *
 * IMPORTANT: under reduced motion, keep the SAME motion tree and pass
 * `initial={false}` — never return a different static tree. The server
 * renders the animated tree (reduce is unknowable at SSR), and React
 * hydration does not reconcile a differing style attribute, so a swapped
 * static tree leaves elements stuck at their hidden initial styles.
 * `initial={false}` renders at the target state and Motion's mount effect
 * overwrites any stale SSR style.
 */

import { type ReactNode } from "react";
import {
  motion,
  useReducedMotion,
  type Variants,
} from "motion/react";

/* Confident expo-out. No overshoot — editorial motion does not bounce. */
export const EASE = [0.16, 1, 0.3, 1] as const;
export const EASE_RULE = [0.65, 0, 0.35, 1] as const;

const VIEWPORT = { once: true, margin: "0px 0px -12% 0px" } as const;

/* ---------- TypeSet: a line that rises out of its own baseline ---------- */

const lineVariants: Variants = {
  hidden: { y: "110%" },
  shown: { y: "0%" },
};

export function TypeSet({
  children,
  delay = 0,
  duration = 0.9,
  as = "span",
  className,
  immediate = false,
}: {
  children: ReactNode;
  delay?: number;
  duration?: number;
  as?: "span" | "div";
  className?: string;
  /** Animate on mount instead of on scroll-in — use for above-the-fold (hero)
   *  content, which must never wait on an intersection that may not fire. */
  immediate?: boolean;
}) {
  const reduce = useReducedMotion();
  const Outer = as === "div" ? motion.div : motion.span;
  const trigger = immediate
    ? { animate: "shown" as const }
    : { whileInView: "shown" as const, viewport: VIEWPORT };
  return (
    <Outer
      className={className}
      style={{ display: as === "div" ? "block" : "inline-block", overflow: "hidden" }}
    >
      <motion.span
        style={{ display: "inline-block", willChange: "transform" }}
        variants={lineVariants}
        initial={reduce ? false : "hidden"}
        {...trigger}
        transition={{ duration, ease: EASE, delay }}
      >
        {children}
      </motion.span>
    </Outer>
  );
}

/* ---------- Stagger: a column whose children arrive in sequence ---------- */

export function Stagger({
  children,
  className,
  gap = 0.07,
  delay = 0,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  gap?: number;
  delay?: number;
  as?: "div" | "ul" | "ol";
}) {
  const Comp = as === "ul" ? motion.ul : as === "ol" ? motion.ol : motion.div;
  return (
    <Comp
      className={className}
      initial="hidden"
      whileInView="shown"
      viewport={VIEWPORT}
      variants={{
        hidden: {},
        shown: { transition: { staggerChildren: gap, delayChildren: delay } },
      }}
    >
      {children}
    </Comp>
  );
}

const riseVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  shown: { opacity: 1, y: 0 },
};

export function StaggerItem({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li";
}) {
  const reduce = useReducedMotion();
  const Comp = as === "li" ? motion.li : motion.div;
  return (
    <Comp
      className={className}
      variants={riseVariants}
      initial={reduce ? false : undefined}
      transition={{ duration: 0.6, ease: EASE }}
    >
      {children}
    </Comp>
  );
}

/* ---------- Reveal: a single block that rises on scroll ---------- */

export function Reveal({
  children,
  className,
  delay = 0,
  y = 18,
  as = "div",
  immediate = false,
  id,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
  as?: "div" | "section";
  immediate?: boolean;
  id?: string;
}) {
  const reduce = useReducedMotion();
  const Comp = as === "section" ? motion.section : motion.div;
  const shown = { opacity: 1, y: 0 };
  const trigger = immediate
    ? { animate: shown }
    : { whileInView: shown, viewport: VIEWPORT };
  return (
    <Comp
      id={id}
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      {...trigger}
      transition={{ duration: 0.7, ease: EASE, delay }}
    >
      {children}
    </Comp>
  );
}

/* ---------- Rule: a hairline that draws itself ---------- */

export function Rule({
  className,
  vertical = false,
  delay = 0,
  duration = 0.8,
  immediate = false,
}: {
  className?: string;
  vertical?: boolean;
  delay?: number;
  duration?: number;
  immediate?: boolean;
}) {
  const reduce = useReducedMotion();
  const base = vertical ? "w-px self-stretch bg-border" : "h-px w-full bg-border";
  const shown = vertical ? { scaleY: 1 } : { scaleX: 1 };
  const trigger = immediate ? { animate: shown } : { whileInView: shown, viewport: VIEWPORT };
  return (
    <motion.span
      aria-hidden
      className={`${base} ${className ?? ""}`}
      style={{ transformOrigin: vertical ? "top" : "left", willChange: "transform" }}
      initial={reduce ? false : vertical ? { scaleY: 0 } : { scaleX: 0 }}
      {...trigger}
      transition={{ duration, ease: EASE_RULE, delay }}
    />
  );
}
