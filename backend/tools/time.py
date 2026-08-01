"""Current-clock tool (key: time.current_time) with explicit timezone semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from foundation import PermissionLevel
from registry import tool


class CurrentTimeIn(BaseModel):
    target_zone: str | None = Field(
        default=None,
        description="Optional IANA timezone, such as Asia/Kathmandu; omitted means UTC.",
    )


class CurrentTimeOut(BaseModel):
    result: str = Field(description="Current timezone-aware date and time in ISO 8601 format.")
    zone_used: str = Field(description="IANA timezone used, or UTC when none was requested.")


@tool
class CurrentTimeTool:
    name = "current_time"
    domain = "time"
    description = "Return the current date and time in an optional IANA timezone; defaults to UTC."
    input_schema = CurrentTimeIn
    output_schema = CurrentTimeOut
    permission = PermissionLevel.READ
    tags = ("time", "now", "timezone")

    async def run(self, args: CurrentTimeIn) -> CurrentTimeOut:
        if args.target_zone is None:
            target_zone = timezone.utc
            zone_name = "UTC"
        else:
            try:
                target_zone = ZoneInfo(args.target_zone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError(f"Unknown IANA timezone: {args.target_zone}") from exc
            zone_name = args.target_zone

        return CurrentTimeOut(
            result=datetime.now(target_zone).isoformat(),
            zone_used=zone_name,
        )
