"""
settings — the typed loader for the owner's central `config/` control panel.

Reads the YAML under the repo-root `config/` (the ruled Phase-3 home) into validated,
typed values, failing LOUD at import time on anything malformed or out of range — a bad
config value never silently becomes wrong runtime behavior (LAW 5, fail-closed). This
module holds NO values of its own; every number lives in `config/*.yaml` (one source of
truth, LAW 4). Everything it exposes is BACKEND-CONTROLLED: server-enforced, never
accepted from a client.

Migration note (CENTRAL_CONFIG Phase 3): this is the new typed loader that
`config/README.md` names. It is being populated ONE config area per commit,
behavior-preserving (each default equals today's hardcoded value). The first area is the
budget/margin knobs; plans/limits/model-catalog still load through the older `config/`
package until their areas migrate here and that package is retired (decision D6).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Repo-root config/ — this file is backend/settings.py, so config/ is one level up.
_CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"


def _load_mapping(relpath: str) -> dict:
    """Read one config YAML into a mapping, failing loud if it is missing or malformed —
    a broken control panel must stop startup, never degrade to a guessed default."""
    path = _CONFIG_ROOT / relpath
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"config: required file missing: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"config: {path} did not parse to a mapping (got {type(data).__name__})")
    return data


class BudgetConfig(BaseModel):
    """The spend/margin ceiling + context-history budget knobs (`config/backend/budget.yaml`).

    `spend_ceiling_fraction` is the SINGLE source of the margin invariant (ADR-0004 / the
    Redis atomic budget): a user may spend at most this fraction of what they paid on real
    cost, and the remainder is our guaranteed minimum margin. Read the ceiling ONLY from
    here (`settings.SPEND_CEILING_FRACTION`) — no call site may hardcode or re-derive it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    spend_ceiling_fraction: float = Field(gt=0.0, le=1.0)  # 0 < f ≤ 1; ≥(1-f) is locked margin
    history_char_budget: int = Field(gt=0)                 # chars before oldest turns condense
    verbatim_turn_floor: int = Field(ge=1)                 # most-recent turns always kept whole
    infra_cost_per_call_micros: int = Field(ge=0)          # µ$ flat, every LLM call (B2b)
    infra_cost_per_second_micros: int = Field(ge=0)        # µ$ per wall-clock second (B2b)


def _load_budget() -> BudgetConfig:
    raw = _load_mapping("backend/budget.yaml")
    try:
        return BudgetConfig(**raw)
    except ValidationError as exc:
        # Fail loud with the exact field(s) at fault — never start on an invalid money knob.
        raise RuntimeError(f"config/backend/budget.yaml is invalid:\n{exc}") from exc


class ModelPrice(BaseModel):
    """One model's token cost, in micro-dollars per token (µ$/token)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_micros_per_token: float = Field(ge=0.0)
    output_micros_per_token: float = Field(ge=0.0)


class PricingConfig(BaseModel):
    """Per-model LLM pricing (`config/backend/pricing.yaml`), for the real-cost budget.

    FAIL-CLOSED: `price_for()` raises on a model with no entry — an un-priced model must
    BLOCK a spend, never be charged as free (which would silently blow the margin). Adding
    a model to the roster without a price here is a loud error, by design (decision B3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: dict[str, ModelPrice]

    def price_for(self, model_id: str) -> ModelPrice:
        try:
            return self.models[model_id]
        except KeyError:
            raise KeyError(
                f"no price for model {model_id!r} in config/backend/pricing.yaml — "
                "add it (fail-closed: an un-priced model cannot be charged)"
            ) from None


def _load_pricing() -> PricingConfig:
    raw = _load_mapping("backend/pricing.yaml")
    try:
        return PricingConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/pricing.yaml is invalid:\n{exc}") from exc


BUDGET: BudgetConfig = _load_budget()
PRICING: PricingConfig = _load_pricing()

# The margin invariant's ONE source of truth (ADR-0004). Every ceiling check reads THIS —
# nothing else defines or hardcodes the fraction. Regression-locked in tests/config_budget.py.
SPEND_CEILING_FRACTION: float = BUDGET.spend_ceiling_fraction

__all__ = [
    "BUDGET", "BudgetConfig", "SPEND_CEILING_FRACTION",
    "PRICING", "PricingConfig", "ModelPrice",
]
