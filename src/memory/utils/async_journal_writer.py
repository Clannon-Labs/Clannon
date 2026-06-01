import os
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def atomic_append(path: Path, text: str) -> None:
    """Synchronous fallback for critical atomic appends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


class AsyncJournalWriter:
    """Non-blocking journal writer to offload disk I/O from the agent's thought loop.
    
    Disk I/O is a synchronous, blocking operation that can stall the Python event 
    loop for several milliseconds — or even seconds if the host system is under 
    heavy I/O wait. In an agentic system, 'thought' latency is the most critical 
    metric. If the agent has to wait for a physical write to complete before 
    moving to its next cognitive step, the perceived responsiveness collapses.
    
    This class can use an internal :class:`asyncio.Queue` to decouple the
    *intent* to log from the physical write. The public append path writes
    synchronously so test runs and short-lived commands always flush journals
    before process exit.
    """
    def __init__(self):
        self._queue: asyncio.Queue[tuple[Path, str]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self):
        """Lazy-initialization ensures we don't spin up a background worker 
        until it's actually needed, saving resources on startup.
        """
        if not self._worker_task:
            self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self):
        """Drain queued journal entries."""
        while True:
            try:
                path, text = await self._queue.get()
                atomic_append(path, text)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory journal write failure: {e}", exc_info=True)

    def append(self, path: Path, text: str):
        """Append a journal entry and flush it before returning."""
        atomic_append(path, text)
