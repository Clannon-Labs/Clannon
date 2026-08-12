"""Retained notification implementation, disabled from private-alpha discovery.

Outbound mutation needs separate reviewed policy before re-enablement. Keeping this
implementation preserves replaceability without making it model-reachable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class NotifyIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    destination: str = Field(
        description="The webhook URL to deliver to (a Slack/Discord/Zapier incoming webhook "
        "or a custom endpoint). Must be an external https URL; internal addresses are blocked."
    )
    content: str = Field(description="The message or report content to deliver, inline.")
    instructions: str = Field(
        default="", description="Optional: how to format for this channel or what to emphasize."
    )


@expert
class NotificationExpert:
    name = "notifier"
    domain = "delivery"
    description = "Disabled private-alpha outbound delivery implementation."
    input_schema = NotifyIn
    output_schema = ExpertOutput
    skills = ("skills",)               # baseline skills/ beside this file
    tools = ("http.request",)          # the outbound delivery channel (SSRF-guarded)
    model_role = "research"            # light formatting + a tool call
    permission = PermissionLevel.NETWORK
    tags = ("delivery", "notification", "webhook")

    async def run(self, args: NotifyIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: NotifyIn, env: ExpertEnv) -> str:
    """This expert's per-call task: deliver `content` to `destination`, with any
    channel-specific formatting instructions. Structured fields, not free-form text."""
    extra = f"\n\nFormatting notes: {args.instructions}" if args.instructions.strip() else ""
    return (
        f"Deliver the following content to this webhook destination: {args.destination}\n\n"
        f"--- content to deliver ---\n{args.content}\n--- end content ---{extra}"
    )
