from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _intent(**overrides) -> OrderIntent:
    base = {
        "intent_id": "intent_1",
        "trace_id": "trace_1",
        "run_id": "run_1",
        "strategy_id": "funding_v1",
        "config_hash": "config_hash",
        "idempotency_key": "idem_1",
        "symbol": "BTCUSDT",
        "leg": OrderIntentLeg.SPOT_OPEN,
        "side": OrderSide.BUY,
        "quantity": Decimal("0.01"),
        "notional_quote": Decimal("1000"),
        "limit_price": Decimal("100000"),
        "client_order_id": "client_1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(overrides)
    return OrderIntent(**base)


def test_order_intent_computes_residual_quantity() -> None:
    intent = _intent(filled_quantity=Decimal("0.004"))

    assert intent.residual_quantity == Decimal("0.006")
    assert intent.is_terminal is False


def test_order_intent_rejects_missing_ids() -> None:
    with pytest.raises(ValueError, match="trace_id is required"):
        _intent(trace_id="")


def test_order_intent_rejects_non_positive_amounts() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        _intent(quantity=Decimal("0"))


def test_order_intent_rejects_overfilled_quantity() -> None:
    with pytest.raises(ValueError, match="filled_quantity cannot exceed quantity"):
        _intent(filled_quantity=Decimal("0.02"))


def test_order_intent_marks_terminal_state() -> None:
    intent = _intent(state=OrderIntentState.CANCELLED)

    assert intent.is_terminal is True
