"""Server-owned memory access derived from central plan configuration."""

from __future__ import annotations

from foundation import MemoryStore

from . import config


_DURABLE_TIERS = frozenset(MemoryStore) - {MemoryStore.WORKING}


def allowed_memory_tiers(plan_id: str | None) -> tuple[MemoryStore, ...]:
    """Return configured durable tiers for one exact plan id.

    Missing, duplicated, or malformed plan data returns no entitlement. Runtime
    authorization must never turn config uncertainty into free-plan or all-tier
    access.
    """
    if not isinstance(plan_id, str) or not plan_id:
        return ()
    matches = [
        plan
        for plan in config.PLANS
        if isinstance(plan, dict) and plan.get("id") == plan_id
    ]
    if len(matches) != 1:
        return ()

    raw_tiers = matches[0].get("memoryTiers")
    if not isinstance(raw_tiers, list):
        return ()
    try:
        tiers = tuple(MemoryStore(value) for value in raw_tiers)
    except (TypeError, ValueError):
        return ()
    if len(set(tiers)) != len(tiers) or any(
        tier not in _DURABLE_TIERS for tier in tiers
    ):
        return ()
    return tiers
