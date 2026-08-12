import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ApiError } from "@/lib/api/types";

let mockWaitlistEnabled = true;
let mockSearchParams = new URLSearchParams();
const routerPush = vi.fn();
const signupMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ setQueryData: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  getClient: () => ({ signup: signupMock }),
  ApiError,
}));

vi.mock("@/lib/api/hooks", () => ({
  queryKeys: { me: ["me"] },
  useWaitlistEnabled: () => mockWaitlistEnabled,
}));

vi.mock("@/components/auth/oauth-buttons", () => ({
  OAuthButtons: () => null,
}));

import SignupPage from "@/app/(auth)/signup/page";

beforeEach(() => {
  mockWaitlistEnabled = true;
  mockSearchParams = new URLSearchParams();
  routerPush.mockClear();
  signupMock.mockReset();
});

describe("signup page — private-alpha gate branching", () => {
  it("shows the invite-only state when no token is present and the gate is on", () => {
    render(<SignupPage />);
    expect(screen.getByRole("heading", { name: "Private alpha" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Join the waitlist" })).toHaveAttribute(
      "href",
      "/waitlist",
    );
    // never renders a form that would 403 on submit
    expect(screen.queryByLabelText(/^Email/)).not.toBeInTheDocument();
  });

  it("shows the open form when the flag is explicitly false", () => {
    mockWaitlistEnabled = false;
    render(<SignupPage />);
    expect(screen.getByRole("heading", { name: "Plant the first ring" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Email/)).toBeInTheDocument();
  });

  it("fails closed (gated) when the flag is unset/unknown, even though useWaitlistEnabled is mocked directly here", () => {
    // useWaitlistEnabled itself owns the fail-closed collapse (tested in
    // hooks); this test documents that the page trusts that hook's boolean
    // rather than re-deriving its own default.
    mockWaitlistEnabled = true;
    render(<SignupPage />);
    expect(screen.getByRole("heading", { name: "Private alpha" })).toBeInTheDocument();
  });

  it("with an approvalToken, shows the name+password form and never asks for email", () => {
    mockSearchParams = new URLSearchParams("approvalToken=tok_abc");
    render(<SignupPage />);
    expect(screen.getByRole("heading", { name: "You're in" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Email/)).not.toBeInTheDocument();
  });

  it("submits name, password, and the URL's approvalToken — never a fabricated email", async () => {
    mockSearchParams = new URLSearchParams("approvalToken=tok_abc");
    signupMock.mockResolvedValue({ id: "u_1", name: "New", email: "you@studio.com", plan: "free" });
    render(<SignupPage />);

    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "New Operator" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: /create my workspace/i }));

    await waitFor(() => expect(signupMock).toHaveBeenCalledWith({
      name: "New Operator",
      password: "correct-horse",
      approvalToken: "tok_abc",
    }));
    await waitFor(() => expect(routerPush).toHaveBeenCalledWith("/app"));
  });

  it("shows the invalid-link state (not the generic error banner) on a 403, with no resend action", async () => {
    mockSearchParams = new URLSearchParams("approvalToken=stale_token");
    signupMock.mockRejectedValue(new ApiError("This invite link is invalid or has expired.", 403));
    render(<SignupPage />);

    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "New Operator" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: /create my workspace/i }));

    expect(await screen.findByRole("heading", { name: "Invite link expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resend/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Join the waitlist" })).toHaveAttribute(
      "href",
      "/waitlist",
    );
  });

  it("open form: a surprise 403 (gate flipped on server-side) redirects to /waitlist instead of dead-ending", async () => {
    mockWaitlistEnabled = false;
    signupMock.mockRejectedValue(
      new ApiError("Signups are invite-only right now. Join the waitlist.", 403),
    );
    render(<SignupPage />);

    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "New Operator" } });
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "you@studio.com" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: /create my workspace/i }));

    await waitFor(() => expect(routerPush).toHaveBeenCalledWith("/waitlist"));
  });
});
