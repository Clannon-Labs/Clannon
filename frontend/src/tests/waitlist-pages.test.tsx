import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ApiError } from "@/lib/api/types";

const joinMock = vi.fn();
const resendMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getClient: () => ({ joinWaitlist: joinMock, resendWaitlistVerification: resendMock }),
  ApiError,
}));

import WaitlistPage from "@/app/(auth)/waitlist/page";
import WaitlistInvalidLinkPage from "@/app/(auth)/waitlist/invalid-link/page";
import WaitlistConfirmedPage from "@/app/(auth)/waitlist/confirmed/page";

beforeEach(() => {
  joinMock.mockReset();
  resendMock.mockReset();
});

describe("/waitlist join page", () => {
  it("shows non-oracle success copy — never claims the address IS on the list", async () => {
    joinMock.mockResolvedValue(undefined);
    render(<WaitlistPage />);
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "you@studio.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Join the waitlist" }));

    expect(await screen.findByRole("heading", { name: "Check your inbox" })).toBeInTheDocument();
    const body = screen.getByText(/confirmation link/);
    // the honest "if" framing, not an assertion of fact
    expect(body.textContent).toMatch(/If that address can join/);
    expect(joinMock).toHaveBeenCalledWith({ email: "you@studio.com", note: undefined });
  });

  it("trims and forwards an optional note", async () => {
    joinMock.mockResolvedValue(undefined);
    render(<WaitlistPage />);
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "you@studio.com" } });
    fireEvent.change(screen.getByLabelText(/What are you hoping/), {
      target: { value: "  building an agency  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Join the waitlist" }));

    await waitFor(() =>
      expect(joinMock).toHaveBeenCalledWith({ email: "you@studio.com", note: "building an agency" }),
    );
  });

  it("surfaces a real rate-limit error instead of the success screen", async () => {
    joinMock.mockRejectedValue(new ApiError("Too many attempts — wait a minute and try again.", 429));
    render(<WaitlistPage />);
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "you@studio.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Join the waitlist" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts — wait a minute and try again.",
    );
    expect(screen.queryByRole("heading", { name: "Check your inbox" })).not.toBeInTheDocument();
  });
});

describe("/waitlist/invalid-link page", () => {
  it("offers a resend form, and never claims the resend succeeded for a specific address", async () => {
    resendMock.mockResolvedValue(undefined);
    render(<WaitlistInvalidLinkPage />);
    expect(screen.getByRole("heading", { name: "Link expired" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "you@studio.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Resend confirmation link" }));

    expect(await screen.findByRole("heading", { name: "Check your inbox" })).toBeInTheDocument();
    expect(resendMock).toHaveBeenCalledWith("you@studio.com");
  });
});

describe("/waitlist/confirmed page", () => {
  it("confirms the EMAIL, not approval — must not promise access", () => {
    render(<WaitlistConfirmedPage />);
    expect(screen.getByRole("heading", { name: "Email confirmed" })).toBeInTheDocument();
    expect(screen.getByText(/owner reviews requests individually/)).toBeInTheDocument();
  });
});
