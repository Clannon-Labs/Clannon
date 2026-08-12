import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourcesPanel } from "@/components/app/expert-panel";
import type { Source } from "@/lib/api/types";

const source = (id: string, url: string): Source => ({
  id,
  title: `Source ${id}`,
  url,
  domain: "example.com",
});

describe("citation render boundary", () => {
  it.each([
    "javascript:alert(document.domain)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "blob:https://clannon.com/id",
  ])("never renders dangerous scheme %s as a link", (url) => {
    render(<SourcesPanel sources={[source("unsafe", url)]} />);
    const item = screen.getByRole("listitem");
    expect(within(item).queryByRole("link")).not.toBeInTheDocument();
    expect(item.querySelector("[data-invalid-source-url]")).toBeInTheDocument();
  });

  it.each(["https://example.com/report", "http://localhost:8080/source"])(
    "keeps valid HTTP(S) citation %s clickable",
    (url) => {
      render(<SourcesPanel sources={[source("safe", url)]} />);
      expect(screen.getByRole("link", { name: /Source safe/ })).toHaveAttribute("href", url);
    },
  );
});
