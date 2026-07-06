"""
core/memory/tiers.py

Per-tier ranking weight (`TIER_TRUST`) and hydration-budget floor
(`TIER_FLOOR`) — the two `MemoryStore`-keyed dicts both the read side
(`hydration.py`, ranking + water-filling) and the write side
(`write_policy.py`, tagging a new memory's trust) need. A single home so
neither side re-derives the int-cast logic below independently (LAW 1) —
distinct from a bare scalar like `max_content_chars`, which each module
reads directly off `settings.MEMORY` since there's no logic to duplicate,
just a number.
"""
from __future__ import annotations

import settings
from foundation import MemoryStore

# TierTrust's fields are `float` in settings.py (a future fractional weight
# is legitimate there), but these values flow into MemoryItem.trust (an
# `int` field, foundation/contracts/memory.py) and the Qdrant payload — an
# un-cast 3.0 would silently persist as a float where 3 was stored before.
# int() here is the honest boundary cast, not a settings.py schema change.
TIER_TRUST: dict[MemoryStore, int] = {
    MemoryStore.WIKI: int(settings.MEMORY.tier_trust.wiki),
    MemoryStore.SEMANTIC: int(settings.MEMORY.tier_trust.semantic),
    MemoryStore.EPISODIC: int(settings.MEMORY.tier_trust.episodic),
    MemoryStore.PROCEDURAL: int(settings.MEMORY.tier_trust.procedural),
}

# Minimum hydration-budget floor per tier (fractions) — ARCHITECTURE.md §4 step 5.
TIER_FLOOR: dict[MemoryStore, float] = {
    MemoryStore.WIKI: settings.MEMORY.tier_floor.wiki,
    MemoryStore.SEMANTIC: settings.MEMORY.tier_floor.semantic,
    MemoryStore.EPISODIC: settings.MEMORY.tier_floor.episodic,
    MemoryStore.PROCEDURAL: settings.MEMORY.tier_floor.procedural,
}
