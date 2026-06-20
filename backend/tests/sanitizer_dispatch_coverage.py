"""
Characterization test for the sanitizer dispatch ladder.

This pins which `Modality` members `runner._MODALITY_WORKERS` currently
dispatches a sanitizer worker for. It is purely additive: it does not touch the
runner, it only records and guards today's behavior.

Why this matters as a security invariant: every *content* modality must reach a
sanitizer worker, otherwise content of that modality would flow into later
stages unsanitized. This test fails the moment a new content modality is added
to the `Modality` enum without a matching worker in the dispatch ladder.

The one `Modality` member with no worker is `UNSUPPORTED_MODALITY`. That is the
explicit "no worker" sentinel, not a gap: the runner maps no worker to it and
instead blocks with `BlockReason.UNSUPPORTED_MODALITY` when a flow's detected
modalities resolve to no scheduled worker (the `if not tasks:` path in
`runner.run`). Its exclusion is intentional and is asserted here so a future
reader can tell "deliberately unhandled" apart from "accidentally dropped".
"""

from foundation import Modality
from security.sanitizers import runner


# The modalities the dispatch ladder handles today, captured from the runner as
# it currently stands. Changing the ladder should be a deliberate update here.
HANDLED_MODALITIES = {
    Modality.TEXT,
    Modality.PDF,
    Modality.IMAGE,
    Modality.AUDIO,
    Modality.VIDEO,
}

# Modality members intentionally NOT dispatched to a worker (see module docstring).
UNHANDLED_BY_DESIGN = {Modality.UNSUPPORTED_MODALITY}


def test_dispatch_ladder_handles_the_pinned_modality_set():
    """`_MODALITY_WORKERS` keys map exactly onto the pinned set of handled modalities."""
    dispatched = {Modality(key) for key in runner._MODALITY_WORKERS}
    assert dispatched == HANDLED_MODALITIES


def test_every_modality_is_handled_or_unhandled_by_design():
    """
    No content modality slips through unsanitized. Every `Modality` member is
    either dispatched to a worker or is the explicit `UNSUPPORTED_MODALITY`
    sentinel. A new content modality added to the enum without a worker fails
    here, surfacing the coverage gap before it ships.
    """
    accounted_for = HANDLED_MODALITIES | UNHANDLED_BY_DESIGN
    assert set(Modality) == accounted_for
