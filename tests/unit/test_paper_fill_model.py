from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot
from degenking.orders.intents import OrderIntent, OrderIntentLeg, OrderSide
from degenking.paper.fill_model import PaperFillStatus, simulate_limit_fill

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _book(**overrides) -> OrderBookSnapshot:
    base = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "market_type": MarketType.SPOT,
        "bids": (
            OrderBookLevel(price=Decimal("99"), quantity=Decimal("2")),
            OrderBookLevel(price=Decimal("98"), quantity=Decimal("2")),
        ),
        "asks": (
            OrderBookLevel(price=Decimal("101"), quantity=Decimal("2")),
            OrderBookLevel(price=Decimal("102"), quantity=Decimal("2")),
        ),
        "observed_at": NOW,
    }
    base.update(overrides)
    return OrderBookSnapshot(**base)


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
    }
    base.update(overrides)
    return OrderIntent(**base)


def test_simulate_buy_limit_fill_full() -> None:
    result = simulate_limit_fill(
        _intent(),
        _book(),
        taker_fee_bps=Decimal("10"),
    )

    assert result.status == PaperFillStatus.FULL_FILL
    assert result.filled_quantity == Decimal("1")
    assert result.remaining_quantity == Decimal("0")
    assert result.filled_notional_quote == Decimal("101")
    assert result.average_price == Decimal("101")
    assert result.fee_quote == Decimal("0.101")
    assert result.slippage_quote == Decimal("1")
    assert result.slippage_bps == Decimal("99.00990099009900990099009901")


def test_simulate_sell_limit_fill_full() -> None:
    result = simulate_limit_fill(
        _intent(side=OrderSide.SELL, limit_price=Decimal("99")),
        _book(),
        taker_fee_bps=Decimal("5"),
    )

    assert result.status == PaperFillStatus.FULL_FILL
    assert result.filled_notional_quote == Decimal("99")
    assert result.average_price == Decimal("99")
    assert result.fee_quote == Decimal("0.0495")
    assert result.slippage_quote == Decimal("1")


def test_simulate_fill_ratio_forces_partial_fill() -> None:
    result = simulate_limit_fill(
        _intent(),
        _book(),
        taker_fee_bps=Decimal("0"),
        fill_ratio=Decimal("0.25"),
    )

    assert result.status == PaperFillStatus.PARTIAL_FILL
    assert result.filled_quantity == Decimal("0.25")
    assert result.remaining_quantity == Decimal("0.75")
    assert result.fully_filled is False


def test_limit_price_can_prevent_fill() -> None:
    result = simulate_limit_fill(
        _intent(limit_price=Decimal("100")),
        _book(),
        taker_fee_bps=Decimal("0"),
    )

    assert result.status == PaperFillStatus.NO_FILL
    assert result.filled_quantity == Decimal("0")
    assert result.average_price is None


def test_orderbook_depth_can_create_partial_fill() -> None:
    shallow_book = _book(
        asks=(OrderBookLevel(price=Decimal("101"), quantity=Decimal("0.4")),)
    )

    result = simulate_limit_fill(
        _intent(),
        shallow_book,
        taker_fee_bps=Decimal("0"),
    )

    assert result.status == PaperFillStatus.PARTIAL_FILL
    assert result.filled_quantity == Decimal("0.4")
    assert result.remaining_quantity == Decimal("0.6")


def test_rejects_symbol_mismatch() -> None:
    with pytest.raises(ValueError, match="orderbook symbol must match"):
        simulate_limit_fill(
            _intent(),
            _book(symbol="ETHUSDT"),
            taker_fee_bps=Decimal("0"),
        )


def test_rejects_invalid_fill_ratio() -> None:
    with pytest.raises(ValueError, match="fill_ratio"):
        simulate_limit_fill(
            _intent(),
            _book(),
            taker_fee_bps=Decimal("0"),
            fill_ratio=Decimal("0"),
        )


def test_rejects_negative_fee() -> None:
    with pytest.raises(ValueError, match="taker_fee_bps"):
        simulate_limit_fill(
            _intent(),
            _book(),
            taker_fee_bps=Decimal("-1"),
        )
