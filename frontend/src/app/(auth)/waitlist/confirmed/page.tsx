import { MailCheck } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";

/**
 * Redirect target for `GET /waitlist/verify` on success (`backend/api/waitlist.py`).
 * A real visitor never types this URL — the mailed link lands here after the
 * backend consumes the verify token. Confirms the EMAIL, not access: approval
 * is a separate, owner-only step, so this page must not promise a spot.
 */
export default function WaitlistConfirmedPage() {
  return (
    <div className="animate-fade-up text-center">
      <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
      <h1 className="display-soft mt-5 text-2xl">Email confirmed</h1>
      <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
        You&apos;re on the Clannon waitlist. The owner reviews requests individually —
        we&apos;ll email you an invite link the moment there&apos;s room.
      </p>
      <ButtonLink href="/" variant="outline" className="mt-8">
        Back to the site
      </ButtonLink>
    </div>
  );
}
