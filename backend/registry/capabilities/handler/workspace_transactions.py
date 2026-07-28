"""Keyed transactions for persistent expert workspaces."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class _WorkspaceTransactions:
    """Mission workspace locks shared by every handler/scoped-handler instance."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str, str], tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def hold(self, key: tuple[str, str, str]):
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            await lock.acquire()
        except BaseException:
            self._drop_user(key, lock)
            raise
        try:
            yield
        finally:
            lock.release()
            self._drop_user(key, lock)

    def _drop_user(self, key: tuple[str, str, str], lock: asyncio.Lock) -> None:
        current = self._locks.get(key)
        if current is None or current[0] is not lock:
            return
        users = current[1] - 1
        if users:
            self._locks[key] = (lock, users)
        else:
            del self._locks[key]


_WORKSPACE_TRANSACTIONS = _WorkspaceTransactions()
