from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.depth import (
    BookSide,
    estimate_slippage_for_notional,
    has_min_depth,
)
from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot

OBSERVED_AT = datetime(2026, 5, 18, tzinfo=UTC)


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(
            OrderBookLevel(price=Decimal("99"), quantity=Decimal("5")),
            OrderBookLevel(price=Decimal("98"), quantity=Decimal("5")),
        ),
        asks=(
            OrderBookLevel(price=Decimal("101"), quantity=Decimal("5")),
            OrderBookLevel(price=Decimal("102"), quantity=Decimal("5")),
        ),
        observed_at=OBSERVED_AT,
    )


def test_buy_slippage_walks_asks_for_full_fill() -> None:
    estimate = estimate_slippage_for_notional(
        _book(),
        side=BookSide.BUY,
        notional_quote=Decimal("606"),
        reference_price=Decimal("100"),
    )

    assert estimate.fully_filled is True
    assert estimate.filled_notional_quote == Decimal("606")
    assert estimate.filled_quantity == Decimal("5.990196078431372549019607843")
    assert estimate.average_price == Decimal("101.1653027823240589198036007")
    assert estimate.slippage_quote == Decimal("6.980392156862745098039215958")
    assert estimate.slippage_bps == Decimal("115.1879893871740115187989432")
    assert estimate.levels_consumed == 2


def test_sell_slippage_walks_bids_for_full_fill() -> None:
    estimate = estimate_slippage_for_notional(
        _book(),
        side=BookSide.SELL,
        notional_quote=Decimal("588"),
        reference_price=Decimal("100"),
    )

    assert estimate.fully_filled is True
    assert estimate.filled_notional_quote == Decimal("588")
    assert estimate.filled_quantity == Decimal("5.948979591836734693877551020")
    assert estimate.average_price == Decimal("98.84048027444253859348198972")
    assert estimate.slippage_quote == Decimal("6.897959183673469387755101971")
    assert estimate.slippage_bps == Decimal("117.3122310148549215604609179")
    assert estimate.levels_consumed == 2


def test_partial_fill_when_depth_is_insufficient() -> None:
    estimate = estimate_slippage_for_notional(
        _book(),
        side=BookSide.BUY,
        notional_quote=Decimal("2000"),
        reference_price=Decimal("100"),
    )

    assert estimate.fully_filled is False
    assert estimate.filled_notional_quote == Decimal("1015")
    assert estimate.filled_quantity == Decimal("10")
    assert estimate.levels_consumed == 2


def test_reference_price_defaults_to_mid() -> None:
    estimate = estimate_slippage_for_notional(
        _book(),
        side=BookSide.BUY,
        notional_quote=Decimal("101"),
    )

    assert estimate.reference_price == Decimal("100")
    assert estimate.average_price == Decimal("101")


def test_has_min_depth_uses_requested_side_only() -> None:
    assert has_min_depth(_book(), side=BookSide.BUY, min_depth_quote=Decimal("1015"))
    assert not has_min_depth(_book(), side=BookSide.BUY, min_depth_quote=Decimal("1016"))
    assert has_min_depth(_book(), side=BookSide.SELL, min_depth_quote=Decimal("985"))
    assert not has_min_depth(_book(), side=BookSide.SELL, min_depth_quote=Decimal("986"))


def test_rejects_non_positive_notional() -> None:
    with pytest.raises(ValueError, match="notional_quote"):
        estimate_slippage_for_notional(
            _book(),
            side=BookSide.BUY,
            notional_quote=Decimal("0"),
        )


def test_empty_book_cannot_infer_reference_price() -> None:
    empty_book = OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(),
        asks=(),
        observed_at=OBSERVED_AT,
    )

    with pytest.raises(ValueError, match="reference price"):
        estimate_slippage_for_notional(
            empty_book,
            side=BookSide.BUY,
            notional_quote=Decimal("1"),
        )


def test_negative_quantity_is_rejected() -> None:
    bad_book = OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(OrderBookLevel(price=Decimal("99"), quantity=Decimal("1")),),
        asks=(OrderBookLevel(price=Decimal("101"), quantity=Decimal("-1")),),
        observed_at=OBSERVED_AT,
    )

    with pytest.raises(ValueError, match="quantity"):
        estimate_slippage_for_notional(
            bad_book,
            side=BookSide.BUY,
            notional_quote=Decimal("1"),
        )
