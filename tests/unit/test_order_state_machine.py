from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.orders.state_machine import (
    IllegalOrderStateTransitionError,
    transition_intent,
)

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=1)


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


def test_normal_order_intent_state_path() -> None:
    intent = _intent()
    intent = transition_intent(intent, OrderIntentState.RISK_APPROVED, updated_at=LATER)
    intent = transition_intent(
        intent,
        OrderIntentState.SUBMITTED_TO_PAPER_BROKER,
        updated_at=LATER,
    )
    intent = transition_intent(intent, OrderIntentState.ACKNOWLEDGED, updated_at=LATER)
    intent = transition_intent(
        intent,
        OrderIntentState.FILLED,
        updated_at=LATER,
        filled_quantity=Decimal("0.01"),
    )
    intent = transition_intent(intent, OrderIntentState.RECONCILED, updated_at=LATER)
    intent = transition_intent(intent, OrderIntentState.POSITION_UPDATED, updated_at=LATER)
    intent = transition_intent(intent, OrderIntentState.CLOSED, updated_at=LATER)

    assert intent.state == OrderIntentState.CLOSED
    assert intent.is_terminal is True


def test_partial_fill_path_preserves_residual_quantity() -> None:
    intent = transition_intent(
        _intent(state=OrderIntentState.ACKNOWLEDGED),
        OrderIntentState.PARTIALLY_FILLED,
        updated_at=LATER,
        filled_quantity=Decimal("0.004"),
    )

    assert intent.filled_quantity == Decimal("0.004")
    assert intent.residual_quantity == Decimal("0.006")


def test_illegal_state_transition_is_rejected() -> None:
    with pytest.raises(
        IllegalOrderStateTransitionError,
        match="illegal order intent transition",
    ):
        transition_intent(
            _intent(),
            OrderIntentState.FILLED,
            updated_at=LATER,
            filled_quantity=Decimal("0.01"),
        )


def test_filled_state_requires_full_fill_quantity() -> None:
    with pytest.raises(ValueError, match="filled intent must have filled_quantity"):
        transition_intent(
            _intent(state=OrderIntentState.ACKNOWLEDGED),
            OrderIntentState.FILLED,
            updated_at=LATER,
            filled_quantity=Decimal("0.004"),
        )


def test_partial_fill_requires_partial_quantity() -> None:
    with pytest.raises(ValueError, match="partial fill requires"):
        transition_intent(
            _intent(state=OrderIntentState.ACKNOWLEDGED),
            OrderIntentState.PARTIALLY_FILLED,
            updated_at=LATER,
            filled_quantity=Decimal("0.01"),
        )


def test_terminal_state_cannot_transition() -> None:
    with pytest.raises(IllegalOrderStateTransitionError):
        transition_intent(
            _intent(state=OrderIntentState.CANCELLED),
            OrderIntentState.CLOSED,
            updated_at=LATER,
        )
