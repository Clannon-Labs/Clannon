/**
 * Tests for HydrationPanel — the "second-session moment" moat surface.
 *
 * Pins the three observable contracts from UI_SPEC §7:
 *   (a) Provenance on demand: tier label, trust line, confidence, source, runId
 *   (b) One-tap correct/delete affordance: wiki => "Wrong — fix it" link;
 *       inferred (non-wiki) => "That's outdated" button; clicking fires the
 *       delete mutation and immediately removes the entry from view.
 *   (c) Recedes to a chip the instant typing starts — full panel gone,
 *       "Picking up where we left off" chip visible, no provenance buttons.
 *
 * The component is driven by the useMemoryEntries hook; that hook is mocked
 * here so the tests are hermetic (no network, no QueryClient, no real client).
 * If a test fails, it means the component's observed behaviour diverged from
 * the contract — investigate whether the component or the spec moved.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// ---- Mocks ------------------------------------------------------------------

vi.mock("motion/react", () => {
  // Plain passthroughs — forward children + className and DROP the animation
  // props so they never reach the DOM. Must cover every motion.<tag> the
  // component renders (currently div, li, p, span); a missing tag resolves to
  // undefined and crashes the render with "element type is invalid".
  type P = { children?: React.ReactNode; className?: string };
  return {
    motion: {
      div: ({ children, className }: P) => <div className={className}>{children}</div>,
      li: ({ children, className }: P) => <li className={className}>{children}</li>,
      p: ({ children, className }: P) => <p className={className}>{children}</p>,
      span: ({ children, className }: P) => <span className={className}>{children}</span>,
    },
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    useReducedMotion: () => true,
  };
});

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string;
    children?: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/brand/memory-rings", () => ({
  MemoryRings: ({ active }: { active?: string | null }) => (
    <div data-testid="memory-rings" data-active={active ?? ""} />
  ),
}));

vi.mock("@/components/motion", () => ({
  EASE: [0.4, 0, 0.2, 1],
  Rule: ({ className }: { className?: string }) => <hr className={className} />,
  TypeSet: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Stagger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Reveal: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: vi.fn(() => vi.fn()),
}));

const mockDeleteMutate = vi.fn();

vi.mock("@/lib/api/hooks", () => ({
  useMemoryEntries: vi.fn(),
  // the chip's "N in reach" now comes from the Manager's dry-run ranking
  // (GET /memory/hydration-preview), not a local re-rank — mock it per test
  useHydrationPreview: vi.fn(),
  useDeleteMemory: vi.fn(() => ({
    mutate: mockDeleteMutate,
    isPending: false,
  })),
}));

// ---- Imports ----------------------------------------------------------------

import { HydrationPanel } from "@/components/app/hydration-panel";
import { useHydrationPreview, useMemoryEntries } from "@/lib/api/hooks";
import type { HydrationPreviewEntry, MemoryEntry } from "@/lib/api/types";

// ---- Fixtures ---------------------------------------------------------------

const WIKI_ENTRY: MemoryEntry = {
  id: "m_wiki_1",
  tier: "wiki",
  title: "Client: ACME Corp — context",
  content: "A multinational widget manufacturer, $6M ARR, founder-led.",
  updatedAt: "2026-06-01T00:00:00.000Z",
};

const SEMANTIC_ENTRY: MemoryEntry = {
  id: "m_sem_1",
  tier: "semantic",
  title: "Preferred format: bullet summaries",
  content: "User prefers bullet-point summaries over paragraphs.",
  updatedAt: "2026-06-01T00:00:00.000Z",
  confidence: 0.85,
  source: "inferred from 3 runs",
};

const EPISODIC_ENTRY: MemoryEntry = {
  id: "m_epi_1",
  tier: "episodic",
  title: "Delivered: ACME market report",
  content: "2 experts, 12k tokens, 5 sources.",
  updatedAt: "2026-06-01T00:00:00.000Z",
  runId: "run_abc123",
};

// ---- Helpers ----------------------------------------------------------------

function setupEntries(entries: MemoryEntry[]) {
  vi.mocked(useMemoryEntries).mockReturnValue({ data: entries, isLoading: false } as ReturnType<
    typeof useMemoryEntries
  >);
}

function setupPreview(hits: HydrationPreviewEntry[] | undefined) {
  vi.mocked(useHydrationPreview).mockReturnValue({ data: hits, isLoading: false } as ReturnType<
    typeof useHydrationPreview
  >);
}

// ---- Tests ------------------------------------------------------------------

describe("HydrationPanel", () => {
  beforeEach(() => {
    setupEntries([WIKI_ENTRY, SEMANTIC_ENTRY, EPISODIC_ENTRY]);
    setupPreview(undefined); // no dry-run hits unless a test provides them
  });

  // --- Loading / null state -------------------------------------------------

  it("renders nothing while entries are still loading (data=undefined)", () => {
    vi.mocked(useMemoryEntries).mockReturnValue({ data: undefined } as ReturnType<
      typeof useMemoryEntries
    >);
    const { container } = render(<HydrationPanel brief="" />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the resting colleague recap when no brief is typed", () => {
    render(<HydrationPanel brief="" />);
    expect(screen.getByText(/Picking up where we left off/i)).toBeInTheDocument();
  });

  it("shows the empty-state message for an empty memory store", () => {
    setupEntries([]);
    render(<HydrationPanel brief="" />);
    expect(screen.getByText(/First session on this project/i)).toBeInTheDocument();
  });

  // --- (a) Provenance on demand: tier, trust, confidence, source, runId ----

  describe("provenance panel on demand", () => {
    it("shows the trust line for a wiki entry after clicking provenance button", () => {
      setupEntries([WIKI_ENTRY]);
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      // Wiki trust line
      expect(screen.getByText(/You wrote this/i)).toBeInTheDocument();
    });

    it("shows the trust line for a semantic entry after clicking provenance button", () => {
      setupEntries([SEMANTIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      expect(screen.getByText(/I learned this and kept the source/i)).toBeInTheDocument();
    });

    it("shows the trust line for an episodic entry after clicking provenance button", () => {
      setupEntries([EPISODIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      expect(screen.getByText(/From a past run/i)).toBeInTheDocument();
    });

    it("shows the confidence percentage for entries with confidence set", () => {
      setupEntries([SEMANTIC_ENTRY]); // confidence = 0.85
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      expect(screen.getByText("85%")).toBeInTheDocument();
    });

    it("does NOT show a confidence row when confidence is absent", () => {
      setupEntries([WIKI_ENTRY]); // no confidence field
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      // No "%" character should appear in the provenance panel
      expect(screen.queryByText(/%/)).toBeNull();
    });

    it("shows the source field when entry has a source", () => {
      setupEntries([SEMANTIC_ENTRY]); // source = "inferred from 3 runs"
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      expect(screen.getByText("inferred from 3 runs")).toBeInTheDocument();
    });

    it("shows the runId in the provenance panel for episodic entries", () => {
      setupEntries([EPISODIC_ENTRY]); // runId = "run_abc123"
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/Why do I know this\?/i));
      expect(screen.getByText("run_abc123")).toBeInTheDocument();
    });

    it("toggling the provenance button a second time collapses the panel", () => {
      setupEntries([SEMANTIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      const btn = screen.getByText(/Why do I know this\?/i);
      fireEvent.click(btn); // expand
      expect(screen.getByText(/I learned this/i)).toBeInTheDocument();
      fireEvent.click(btn); // collapse
      expect(screen.queryByText(/I learned this/i)).toBeNull();
    });
  });

  // --- (b) Correct / delete affordance ------------------------------------

  describe("correct / delete affordances", () => {
    it("shows 'Wrong — fix it' link for wiki entries (not a delete button)", () => {
      setupEntries([WIKI_ENTRY]);
      render(<HydrationPanel brief="" />);
      // Wiki entries get an edit link, not a delete button
      expect(screen.getByText(/Wrong.*fix it/i)).toBeInTheDocument();
      expect(screen.queryByText(/That.s outdated/i)).toBeNull();
    });

    it("shows 'That's outdated' button for inferred (non-wiki) entries", () => {
      setupEntries([SEMANTIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      expect(screen.getByText(/That.s outdated/i)).toBeInTheDocument();
      expect(screen.queryByText(/Wrong.*fix it/i)).toBeNull();
    });

    it("calls the delete mutation with the entry id when 'That's outdated' is clicked", () => {
      setupEntries([SEMANTIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      fireEvent.click(screen.getByText(/That.s outdated/i));
      expect(mockDeleteMutate).toHaveBeenCalledWith("m_sem_1", expect.any(Object));
    });

    it("immediately removes the corrected entry from view (optimistic update)", () => {
      setupEntries([SEMANTIC_ENTRY]);
      render(<HydrationPanel brief="" />);
      expect(screen.getByText("Preferred format: bullet summaries")).toBeInTheDocument();
      fireEvent.click(screen.getByText(/That.s outdated/i));
      // The entry is removed immediately via setDismissed — no round-trip needed
      expect(screen.queryByText("Preferred format: bullet summaries")).toBeNull();
    });
  });

  // --- (c) Recedes once typing starts -------------------------------------

  describe("recedes to chip when typing starts", () => {
    it("shows the full resting panel (with provenance buttons) when brief is empty", () => {
      setupEntries([WIKI_ENTRY]);
      render(<HydrationPanel brief="" />);
      expect(screen.getByText(/Why do I know this\?/i)).toBeInTheDocument();
    });

    it("switches to the chip view and hides provenance buttons when brief has tokens", () => {
      setupEntries([WIKI_ENTRY]);
      const { rerender } = render(<HydrationPanel brief="" />);
      // Typing starts
      rerender(<HydrationPanel brief="widget manufacturer market" />);
      // Chip is shown
      expect(screen.getByText("Picking up where we left off")).toBeInTheDocument();
      // Full panel with provenance buttons is gone
      expect(screen.queryByText(/Why do I know this\?/i)).toBeNull();
    });

    it("shows 'N in reach' in the chip when the dry-run ranking returns hits", () => {
      setupEntries([SEMANTIC_ENTRY]);
      setupPreview([{ ...SEMANTIC_ENTRY, score: 0.9 }]);
      const { rerender } = render(<HydrationPanel brief="" />);
      rerender(<HydrationPanel brief="preferred summaries format" />);
      expect(screen.getByText(/1 in reach/i)).toBeInTheDocument();
    });

    it("shows 'listening' in the chip while the dry-run returns nothing", () => {
      setupEntries([EPISODIC_ENTRY]);
      setupPreview([]); // the endpoint's honest empty — never an error surface
      const { rerender } = render(<HydrationPanel brief="" />);
      rerender(<HydrationPanel brief="completely unrelated xyzzy quux" />);
      expect(screen.getByText(/listening/i)).toBeInTheDocument();
    });
  });
});
