"""
Default expert router.

Phase 1: a deterministic strategy that spawns no experts on its own — the
direct-answer path is the spine default, and experts run only when the advisor
explicitly names them. This satisfies the ExpertRouter protocol so the real
router drops in later with no loop change.

TODO (entropy-based routing): embed the query with nomic-embed-text, compare to
per-expert domain centroids, and use Shannon entropy over the similarity
distribution to pick the spawn set (low entropy -> one targeted expert, high
entropy -> several in parallel). Needs Ollama embeddings + defined experts first.
"""

from __future__ import annotations

from foundation import NormalizedInput

from ..schemas import ExpertRequest


class DefaultExpertRouter:
    """Deterministic no-op router (direct-answer default)."""

    def route(self, normalized: NormalizedInput, candidates: list[str]) -> list[ExpertRequest]:
        return []
