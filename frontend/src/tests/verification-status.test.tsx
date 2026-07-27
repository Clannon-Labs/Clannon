import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("motion/react", () => ({
  motion: {
    span: ({ children, className }: { children?: React.ReactNode; className?: string }) => (
      <span className={className}>{children}</span>
    ),
  },
  useReducedMotion: () => true,
}));

import { VerificationStatus } from "@/components/app/verification-status";

describe("VerificationStatus", () => {
  it("renders full VERIFIED wording only for grounded output", () => {
    render(<VerificationStatus state="grounded" />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("qualifies partial output instead of calling it verified", () => {
    render(<VerificationStatus state="partial" />);
    expect(screen.getByText("Partially verified")).toBeInTheDocument();
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  it("renders warning without a seal for ungrounded output", () => {
    const { container } = render(<VerificationStatus state="ungrounded" />);
    expect(screen.getByText("Not grounded")).toBeInTheDocument();
    expect(container.querySelector("svg[aria-label]")).toBeNull();
  });

  it("renders neutral wording when verification is not applicable", () => {
    render(<VerificationStatus state="not_applicable" />);
    expect(screen.getByText("No verification needed")).toBeInTheDocument();
  });

  it("makes no claim when persisted verdict is absent", () => {
    const { container } = render(<VerificationStatus state={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
