"""Server-owned subscription periods, mock settlement, and run admission.

This is a coarse V1 entitlement gate: it checks completed metered usage before a
run is created. One admitted run may overshoot, and concurrent admissions may
both proceed. The separate Redis money-cost broker remains the future per-call,
atomic hard stop; this module neither enables nor substitutes for it.
"""

from __future__ import annotations

import calendar
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import auth, config, runs

router = APIRouter()


class CheckoutRequest(BaseModel):
    """One supported mock purchase. Identity and settlement are never client fields."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["add_on", "upgrade"]
    creditAmount: int | None = Field(default=None, strict=True)
    planId: str | None = Field(default=None, min_length=1, max_length=64)


class ConfirmationRequest(BaseModel):
    """Provider-shaped settlement event accepted only through deployment auth."""

    model_config = ConfigDict(extra="forbid")

    checkoutId: str = Field(min_length=1, max_length=128)
    confirmationId: str = Field(min_length=1, max_length=128)
    outcome: Literal["confirmed", "failed"]


def utc_now() -> datetime:
    """Current aware UTC time; kept as one seam for deterministic period tests."""
    return datetime.now(timezone.utc)


def _month_boundary(year: int, month: int, anchor_day: int) -> date:
    day = min(anchor_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + month - 1 + offset
    shifted_year, zero_based_month = divmod(absolute, 12)
    return shifted_year, zero_based_month + 1


def billing_period(anchor: date, current: date) -> tuple[date, date]:
    """Return ``[start, end)`` for an anniversary anchored to ``anchor.day``.

    Missing days clamp only for that month. The original anchor day is reused in
    later months, so January 31 becomes February 28/29 and then March 31.
    """
    this_month = _month_boundary(current.year, current.month, anchor.day)
    if current >= this_month:
        start = this_month
        end_year, end_month = _shift_month(current.year, current.month, 1)
        end = _month_boundary(end_year, end_month, anchor.day)
    else:
        start_year, start_month = _shift_month(current.year, current.month, -1)
        start = _month_boundary(start_year, start_month, anchor.day)
        end = this_month
    return start, end


def _ensure_schema(db) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS billing_profiles (
            user_id TEXT PRIMARY KEY,
            anchor_date TEXT NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS billing_checkouts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('add_on', 'upgrade')),
            credit_amount INTEGER,
            target_plan_id TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'failed')),
            created_at REAL NOT NULL,
            settled_at REAL,
            confirmation_id TEXT UNIQUE,
            confirmation_outcome TEXT,
            applied_period_start TEXT
        )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS billing_checkouts_by_owner "
        "ON billing_checkouts (user_id, created_at DESC)"
    )


def _account(db, user_id: str):
    row = db.execute(
        "SELECT id, plan, created_at FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(401, "Account no longer exists.")
    return row


def _anchor_date(db, user_id: str, signup_timestamp: float) -> date:
    _ensure_schema(db)
    row = db.execute(
        "SELECT anchor_date FROM billing_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    if row is None:
        anchor = datetime.fromtimestamp(signup_timestamp, tz=timezone.utc).date()
        db.execute(
            "INSERT INTO billing_profiles (user_id, anchor_date, updated_at) VALUES (?,?,?)",
            (user_id, anchor.isoformat(), utc_now().timestamp()),
        )
        return anchor
    try:
        return date.fromisoformat(row["anchor_date"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Billing state is unavailable.") from exc


def _plans() -> dict[str, dict]:
    return {plan["id"]: plan for plan in config.PLANS}


def _add_on_cap() -> int:
    """Conservative cap derived from existing owner-controlled plan budgets."""
    return max((int(plan["tokenBudget"]) for plan in config.PLANS), default=0)


def _run_date(value: str) -> date | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def _period_state(user_id: str, now: datetime | None = None) -> dict:
    current = (now or utc_now()).astimezone(timezone.utc)
    with auth._db() as db:
        account = _account(db, user_id)
        anchor = _anchor_date(db, user_id, account["created_at"])
        start, end = billing_period(anchor, current.date())
        credit_row = db.execute(
            """SELECT COALESCE(SUM(credit_amount), 0) AS total
               FROM billing_checkouts
               WHERE user_id=? AND kind='add_on' AND status='confirmed'
                 AND applied_period_start=?""",
            (user_id, start.isoformat()),
        ).fetchone()
        plan_id = account["plan"]
    plan = _plans().get(plan_id)
    base_budget = int(plan["tokenBudget"]) if plan is not None else 0
    # A corrupt plan cannot be repaired into a positive entitlement by credits.
    # Fail closed on the whole subscription state, not only its base component.
    additional = int(credit_row["total"] or 0) if plan is not None else 0
    return {
        "planId": plan_id,
        "periodStart": start,
        "periodEnd": end,
        "baseBudget": base_budget,
        "additionalCredits": additional,
        "budget": base_budget + additional,
        "today": current.date(),
    }


def _parse_iso_ms(value: str | None) -> int | None:
    """Milliseconds since epoch for one of RunState's ISO timestamp fields, or
    None if unset/unparseable — callers must treat that as "no data", never 0."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _percentile(sorted_values: list[int], pct: float) -> int | None:
    """Linear-interpolation percentile over an already-sorted list. None on an
    empty sample — an empty sample is not a fast one."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    if lo == hi:
        return sorted_values[lo]
    frac = rank - lo
    return int(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def usage_summary(user_id: str) -> dict:
    """Current server-anchored period usage; period end is exclusive."""
    state = _period_state(user_id)
    start = state["periodStart"]
    end = state["periodEnd"]
    by_day = {
        (start + timedelta(days=offset)).isoformat(): 0
        for offset in range((state["today"] - start).days + 1)
    }
    cache_read = 0
    cache_write = 0
    in_period = 0
    first_message_ms: list[int] = []
    total_duration_ms: list[int] = []
    for run in runs.STORE.list_for(user_id, include_superseded=True):
        day = _run_date(run.created_at)
        if day is None or not (start <= day < end):
            continue
        in_period += 1
        key = day.isoformat()
        by_day.setdefault(key, 0)
        by_day[key] += int(getattr(run, "tokens_used", 0) or 0)
        cache_read += int(getattr(run, "cache_read_tokens", 0) or 0)
        cache_write += int(getattr(run, "cache_write_tokens", 0) or 0)
        # Two independent samples, each needing only its own pair of stamps. A
        # report-mode run with no live narration can be `delivered` with real
        # content and still have `first_message_at is None` — that absence is
        # honest, not a bug, and must not disqualify its (perfectly good)
        # totalDurationMs measurement.
        started_ms = _parse_iso_ms(run.started_at)
        first_ms = _parse_iso_ms(run.first_message_at)
        completed_ms = _parse_iso_ms(run.completed_at)
        if started_ms is not None and first_ms is not None:
            first_message_ms.append(first_ms - started_ms)
        if started_ms is not None and completed_ms is not None:
            total_duration_ms.append(completed_ms - started_ms)
    first_message_ms.sort()
    total_duration_ms.sort()
    return {
        "periodStart": start.isoformat(),
        "periodEnd": end.isoformat(),
        "periodEndExclusive": True,
        "baseBudget": state["baseBudget"],
        "additionalCredits": state["additionalCredits"],
        "budget": state["budget"],
        "used": sum(by_day.values()),
        "cacheReadTokens": cache_read,
        "cacheWriteTokens": cache_write,
        "byDay": [{"date": day, "tokens": tokens} for day, tokens in by_day.items()],
        "latency": {
            "inPeriod": in_period,
            "timeToFirstMessageMs": {
                "sampleSize": len(first_message_ms),
                "excluded": in_period - len(first_message_ms),
                "p50": _percentile(first_message_ms, 0.50),
                "p95": _percentile(first_message_ms, 0.95),
            },
            "totalDurationMs": {
                "sampleSize": len(total_duration_ms),
                "excluded": in_period - len(total_duration_ms),
                "p50": _percentile(total_duration_ms, 0.50),
                "p95": _percentile(total_duration_ms, 0.95),
            },
        },
    }


def admit_run(user_id: str) -> None:
    """Refuse a new run before persistence when current-period entitlement is spent."""
    usage = usage_summary(user_id)
    if usage["used"] < usage["budget"]:
        return
    raise HTTPException(
        402,
        {
            "code": "token_budget_exhausted",
            "message": "Token budget exhausted for this billing period.",
            "used": usage["used"],
            "budget": usage["budget"],
            "periodEnd": usage["periodEnd"],
            "periodEndExclusive": True,
            "actions": [
                {"kind": "add_on", "endpoint": "/billing/checkout"},
                {"kind": "upgrade", "endpoint": "/billing/checkout"},
            ],
        },
    )


def _checkout_json(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "creditAmount": row["credit_amount"],
        "planId": row["target_plan_id"],
        "createdAt": datetime.fromtimestamp(row["created_at"], tz=timezone.utc).isoformat(),
        "settledAt": (
            datetime.fromtimestamp(row["settled_at"], tz=timezone.utc).isoformat()
            if row["settled_at"] is not None
            else None
        ),
    }


def _validate_purchase(db, user_id: str, body: CheckoutRequest) -> tuple[int | None, str | None]:
    account = _account(db, user_id)
    if body.kind == "add_on":
        if body.planId is not None or body.creditAmount is None:
            raise HTTPException(422, "Add-on checkout requires only creditAmount.")
        if body.creditAmount <= 0 or body.creditAmount > _add_on_cap():
            raise HTTPException(422, f"creditAmount must be between 1 and {_add_on_cap()}.")
        return body.creditAmount, None

    if body.creditAmount is not None or body.planId is None:
        raise HTTPException(422, "Upgrade checkout requires only planId.")
    target = _plans().get(body.planId)
    if target is None:
        raise HTTPException(422, "Unknown plan.")
    current = _plans().get(account["plan"])
    if int(target["monthlyUsd"]) <= 0 or (
        current is not None
        and int(target["tokenBudget"]) <= int(current["tokenBudget"])
    ):
        raise HTTPException(422, "Selected plan is not an upgrade.")
    return None, body.planId


def _create_checkout(user_id: str, body: CheckoutRequest) -> dict:
    with auth._db() as db:
        _ensure_schema(db)
        credits, plan_id = _validate_purchase(db, user_id, body)
        checkout_id = f"chk_{secrets.token_hex(12)}"
        db.execute(
            """INSERT INTO billing_checkouts
               (id,user_id,kind,credit_amount,target_plan_id,status,created_at)
               VALUES (?,?,?,?,?,'pending',?)""",
            (checkout_id, user_id, body.kind, credits, plan_id, utc_now().timestamp()),
        )
        row = db.execute("SELECT * FROM billing_checkouts WHERE id=?", (checkout_id,)).fetchone()
    return _checkout_json(row)


def _owned_checkout(user_id: str, checkout_id: str) -> dict:
    with auth._db() as db:
        _ensure_schema(db)
        row = db.execute(
            "SELECT * FROM billing_checkouts WHERE id=? AND user_id=?",
            (checkout_id, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Checkout not found.")
    return _checkout_json(row)


def _settle(body: ConfirmationRequest) -> tuple[dict, bool, bool]:
    now = utc_now().astimezone(timezone.utc)
    with auth._db() as db:
        _ensure_schema(db)
        # auth._db() performs additive migrations before returning and may have an
        # open transaction. Commit those, then lock settlement so concurrent webhook
        # retries cannot both observe a pending checkout.
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        replay = db.execute(
            "SELECT * FROM billing_checkouts WHERE confirmation_id=?",
            (body.confirmationId,),
        ).fetchone()
        if replay is not None:
            if replay["id"] != body.checkoutId or replay["confirmation_outcome"] != body.outcome:
                raise HTTPException(
                    409, "Confirmation identifier already belongs to another event."
                )
            return _checkout_json(replay), False, True

        row = db.execute(
            "SELECT * FROM billing_checkouts WHERE id=?", (body.checkoutId,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Checkout not found.")
        if row["status"] != "pending":
            raise HTTPException(409, "Checkout is already settled.")

        if body.outcome == "failed":
            db.execute(
                """UPDATE billing_checkouts
                   SET status='failed', settled_at=?, confirmation_id=?,
                       confirmation_outcome='failed'
                   WHERE id=?""",
                (now.timestamp(), body.confirmationId, body.checkoutId),
            )
            settled = db.execute(
                "SELECT * FROM billing_checkouts WHERE id=?", (body.checkoutId,)
            ).fetchone()
            return _checkout_json(settled), False, False

        account = _account(db, row["user_id"])
        if row["kind"] == "add_on":
            amount = int(row["credit_amount"] or 0)
            if amount <= 0 or amount > _add_on_cap():
                raise HTTPException(409, "Checkout credit is no longer valid.")
            anchor = _anchor_date(db, row["user_id"], account["created_at"])
            period_start, _period_end = billing_period(anchor, now.date())
        else:
            target = _plans().get(row["target_plan_id"])
            current = _plans().get(account["plan"])
            if target is None or (
                current is not None
                and int(target["tokenBudget"]) <= int(current["tokenBudget"])
            ):
                raise HTTPException(409, "Checkout plan is no longer a valid upgrade.")
            db.execute("UPDATE users SET plan=? WHERE id=?", (target["id"], row["user_id"]))
            period_start = now.date()
            db.execute(
                """INSERT INTO billing_profiles (user_id, anchor_date, updated_at)
                   VALUES (?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     anchor_date=excluded.anchor_date, updated_at=excluded.updated_at""",
                (row["user_id"], period_start.isoformat(), now.timestamp()),
            )

        db.execute(
            """UPDATE billing_checkouts
               SET status='confirmed', settled_at=?, confirmation_id=?,
                   confirmation_outcome='confirmed', applied_period_start=?
               WHERE id=?""",
            (now.timestamp(), body.confirmationId, period_start.isoformat(), body.checkoutId),
        )
        settled = db.execute(
            "SELECT * FROM billing_checkouts WHERE id=?", (body.checkoutId,)
        ).fetchone()
    return _checkout_json(settled), True, False


def _authorize_mock_confirmation(secret: str | None) -> None:
    if not config.MOCK_BILLING_ENABLED:
        raise HTTPException(404, "Not found.")
    expected = config.MOCK_BILLING_SECRET
    if not expected:
        raise HTTPException(503, "Mock billing confirmation is not configured.")
    if secret is None or not hmac.compare_digest(secret, expected):
        raise HTTPException(401, "Invalid billing confirmation credentials.")


@router.get("/usage")
def get_usage(user: auth.User = Depends(auth.current_user)) -> dict:
    return usage_summary(user.id)


@router.post("/billing/checkout", status_code=201)
def create_checkout(
    body: CheckoutRequest, user: auth.User = Depends(auth.current_user)
) -> dict:
    return _create_checkout(user.id, body)


@router.get("/billing/checkouts/{checkout_id}")
def get_checkout(
    checkout_id: str, user: auth.User = Depends(auth.current_user)
) -> dict:
    return _owned_checkout(user.id, checkout_id)


@router.post("/billing/portal")
def billing_portal(user: auth.User = Depends(auth.current_user)) -> dict:
    with auth._db() as db:
        _ensure_schema(db)
        account = _account(db, user.id)
        rows = db.execute(
            "SELECT * FROM billing_checkouts WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            (user.id,),
        ).fetchall()
    return {
        "mode": "mock",
        "planId": account["plan"],
        "maxAddOnCredits": _add_on_cap(),
        "checkouts": [_checkout_json(row) for row in rows],
    }


@router.post("/billing/mock/confirm")
def confirm_mock_checkout(
    body: ConfirmationRequest,
    secret: str | None = Header(default=None, alias="X-Clannon-Mock-Billing-Secret"),
) -> dict:
    _authorize_mock_confirmation(secret)
    checkout, applied, replayed = _settle(body)
    return {"checkout": checkout, "applied": applied, "replayed": replayed}
