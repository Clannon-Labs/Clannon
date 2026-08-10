import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArtifactPreview } from "@/components/app/artifact-preview";
import { buildContentSecurityPolicy } from "../../next.config";

const downloadArtifact = vi.fn();

vi.mock("@/lib/api", () => ({
  getClient: () => ({ downloadArtifact }),
}));

describe("PDF preview isolation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    downloadArtifact.mockReset();
  });

  it("opens a blob PDF outside the app and forbids embedded frames", async () => {
    const createObjectURL = vi.fn(() => "blob:https://clannon.com/pdf-id");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    downloadArtifact.mockResolvedValue(new Blob(["%PDF-1.4"], { type: "application/pdf" }));

    const { unmount } = render(
      <ArtifactPreview
        runId="run_1"
        artifact={{
          id: "artifact_1",
          run_id: "run_1",
          name: "source-pack.pdf",
          mime: "application/pdf",
          size: 8,
        }}
        onClose={vi.fn()}
      />,
    );

    const previewLink = await screen.findByRole("link", { name: "Open PDF preview" });
    expect(previewLink).toHaveAttribute("href", "blob:https://clannon.com/pdf-id");
    expect(previewLink).toHaveAttribute("target", "_blank");
    expect(previewLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByTitle("source-pack.pdf")).not.toBeInTheDocument();
    expect(buildContentSecurityPolicy("https://api.clannon.com", false)).toContain(
      "frame-src 'none'",
    );

    unmount();
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:https://clannon.com/pdf-id"));
  });

  it("rejects malformed API origins before they enter connect-src", () => {
    expect(() =>
      buildContentSecurityPolicy("https://api.clannon.com; script-src *", false),
    ).toThrow(/NEXT_PUBLIC_API_BASE_URL must be an absolute/);
  });
});
