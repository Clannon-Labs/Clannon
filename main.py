"""
Local CLI entry point for the active Vraksha pipeline.

There is no HTTP/FastAPI surface yet, so this module exercises the current
runnable path (intake -> sanitizers -> normalizer -> verifier). It reads one
input from the first CLI argument (or stdin) and prints the resulting Flow
summary. Process exit code is non-zero when the flow was blocked or failed.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Load environment before anything constructs provider clients. .env carries
# non-secret config (e.g. CLAMAV_HOST); .env.local holds secrets like the
# provider API key and overrides .env. The provider SDK reads the key from env.
load_dotenv(".env")
load_dotenv(".env.local", override=True)

from core import pipeline


async def _main() -> int:
    raw_input = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    # Identity is set once here, at the entry point, and travels in Flow context.
    user_id = os.getenv("VRAKSHA_USER_ID", "local-user")
    flow = await pipeline.run(raw_input, session_id="cli", user_id=user_id)
    print(flow.summary())
    return 1 if flow.should_stop else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
