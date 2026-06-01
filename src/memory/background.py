from __future__ import annotations

import asyncio
from typing import Any


def run_background_consolidation(messages: list[dict[str, Any]]) -> None:
    from src.memory.consolidation import consolidate_session

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(consolidate_session(messages))
    except RuntimeError:
        asyncio.run(consolidate_session(messages))
