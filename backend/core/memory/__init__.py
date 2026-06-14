"""Memory layer. The MemoryManager is the only public entry point.

`manager` is the process-level singleton used by the app; construct a fresh
MemoryManager() in tests for isolation.
"""

from .manager import MemoryManager, manager

__all__ = ["MemoryManager", "manager"]
