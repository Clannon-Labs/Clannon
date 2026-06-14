"""Platform-notification expert (key: delivery.notifier) — delivers a finished result
to an external channel by POSTing it to a webhook (Slack, Discord, Zapier, or a custom
endpoint). It shapes the payload for the destination, sends it via the http.request
tool (SSRF-guarded), and reports honestly whether the delivery succeeded. It is the
'deliver to channels' step of a workflow. Its behavior lives in its system prompt +
skills beside this file; this module declares what it is and how its request becomes
the task."""

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
    description = (
        "Deliver a finished result to an external channel by POSTing it to a webhook "
        "(Slack/Discord/Zapier/custom): shape the payload for the destination, send it, and "
        "report whether it was delivered."
    )
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
