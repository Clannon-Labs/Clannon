"""Validation and resolution for legacy persisted conversation branches.

New revisions truncate their existing linear session and need no prefix metadata.
Branches created before that correction may still carry exact inherited run IDs;
every read resolves those IDs through the owner-scoped run store before combining
them with branch-local turns.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_PREFIX_TURNS = 10_000
_UNAVAILABLE = (
    "Conversation lineage is unavailable. Start a new conversation or retry from "
    "an earlier readable turn."
)


class LineageError(RuntimeError):
    """Persisted branch metadata is malformed, missing, or not owner-safe."""


def decode_prefix(raw: Any) -> list[str] | None:
    """Decode a nullable SQLite JSON branch prefix, rejecting malformed state."""
    if raw is None:
        return None
    try:
        prefix = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise LineageError(_UNAVAILABLE) from exc
    _validate_ids(prefix)
    return prefix


def encode_prefix(prefix: list[str] | None) -> str | None:
    """Encode explicit branch metadata; ``None`` remains a legacy linear session."""
    if prefix is None:
        return None
    _validate_ids(prefix)
    return json.dumps(prefix)


def resolve_effective_thread(store: Any, user_id: str, run: Any) -> list[Any]:
    """Return inherited prefix plus every turn local to ``run``'s branch.

    Stored prefix IDs are never trusted as authority: each is fetched through the
    same owner-scoped door as GET, and project mismatches fail closed.
    """
    if run.user_id != user_id:
        raise LineageError(_UNAVAILABLE)

    prefix_ids = getattr(run, "lineage_prefix", None)
    local = store.session_turns(user_id, run.session_id or run.id)
    if prefix_ids is None:
        return local

    _validate_ids(prefix_ids)
    local_ids = {turn.id for turn in local}
    if run.id not in local_ids or local_ids.intersection(prefix_ids):
        raise LineageError(_UNAVAILABLE)

    for turn in local:
        if (
            turn.user_id != user_id
            or turn.project_id != run.project_id
            or getattr(turn, "lineage_prefix", None) != prefix_ids
        ):
            raise LineageError(_UNAVAILABLE)

    prefix = []
    for run_id in prefix_ids:
        turn = store.get(user_id, run_id)
        if turn is None or turn.project_id != run.project_id:
            raise LineageError(_UNAVAILABLE)
        prefix.append(turn)
    return prefix + local


def _validate_ids(prefix: Any) -> None:
    if (
        not isinstance(prefix, list)
        or len(prefix) > _MAX_PREFIX_TURNS
        or any(not isinstance(run_id, str) or not run_id for run_id in prefix)
        or len(set(prefix)) != len(prefix)
    ):
        raise LineageError(_UNAVAILABLE)
