from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot
from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.broker import PaperBroker
from degenking.paper.fill_model import PaperFillStatus

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(OrderBookLevel(price=Decimal("99"), quantity=Decimal("2")),),
        asks=(OrderBookLevel(price=Decimal("101"), quantity=Decimal("2")),),
        observed_at=NOW,
    )


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
        "quantity": Decimal("1"),
        "notional_quote": Decimal("101"),
        "limit_price": Decimal("101"),
        "client_order_id": "client_1",
        "created_at": NOW,
        "updated_at": NOW,
        "state": OrderIntentState.RISK_APPROVED,
    }
    base.update(overrides)
    return OrderIntent(**base)


def test_paper_broker_submits_and_fills_risk_approved_intent() -> None:
    result = PaperBroker().submit(
        _intent(),
        _book(),
        submitted_at=NOW,
        taker_fee_bps=Decimal("10"),
    )

    assert result.accepted is True
    assert result.intent.state == OrderIntentState.FILLED
    assert result.intent.exchange_order_id == "paper_client_1"
    assert result.intent.filled_quantity == Decimal("1")
    assert result.fill is not None
    assert result.fill.status == PaperFillStatus.FULL_FILL


def test_paper_broker_keeps_no_fill_acknowledged() -> None:
    result = PaperBroker().submit(
        _intent(limit_price=Decimal("100")),
        _book(),
        submitted_at=NOW,
        taker_fee_bps=Decimal("0"),
    )

    assert result.accepted is True
    assert result.intent.state == OrderIntentState.ACKNOWLEDGED
    assert result.intent.filled_quantity == Decimal("0")
    assert result.fill is not None
    assert result.fill.status == PaperFillStatus.NO_FILL


def test_paper_broker_records_partial_fill() -> None:
    broker = PaperBroker()

    result = broker.submit(
        _intent(),
        _book(),
        submitted_at=NOW,
        taker_fee_bps=Decimal("0"),
        fill_ratio=Decimal("0.25"),
    )

    assert result.intent.state == OrderIntentState.PARTIALLY_FILLED
    assert result.intent.filled_quantity == Decimal("0.25")
    assert result.intent.residual_quantity == Decimal("0.75")
    assert broker.fills_by_intent_id["intent_1"].status == PaperFillStatus.PARTIAL_FILL


def test_paper_broker_suppresses_duplicate_idempotency_key() -> None:
    broker = PaperBroker()

    first = broker.submit(
        _intent(),
        _book(),
        submitted_at=NOW,
        taker_fee_bps=Decimal("0"),
    )
    duplicate = broker.submit(
        _intent(intent_id="intent_2"),
        _book(),
        submitted_at=NOW,
        taker_fee_bps=Decimal("0"),
    )

    assert first.accepted is True
    assert duplicate.accepted is False
    assert duplicate.intent.state == OrderIntentState.DUPLICATE_SUPPRESSED
    assert duplicate.reason == "duplicate_intent_suppressed"


def test_paper_broker_rejects_non_risk_approved_intent() -> None:
    with pytest.raises(ValueError, match="risk-approved"):
        PaperBroker().submit(
            _intent(state=OrderIntentState.INTENT_CREATED),
            _book(),
            submitted_at=NOW,
            taker_fee_bps=Decimal("0"),
        )
