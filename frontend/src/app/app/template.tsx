"use client";

import { motion, useReducedMotion } from "motion/react";
import { EASE } from "@/components/motion";

/**
 * Workspace route transition. `template.tsx` re-mounts on every navigation
 * (unlike layout), so the main content settles in — a gentle rise + fade —
 * while the sidebar and shell (in layout.tsx) stay put. That continuity is
 * what turns run-row → run-page from a reload-feel cut into "the page
 * arrived." Kept subtle (6px, 280ms) so frequent navigation never drags.
 * Reduced motion: an instant, dignified appearance.
 */
export default function WorkspaceTemplate({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
