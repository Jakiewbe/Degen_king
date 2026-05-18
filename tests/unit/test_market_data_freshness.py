from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.common.enums import FreshnessStatus, MarketType
from degenking.market_data.freshness import check_freshness
from degenking.market_data.latency import check_latency
from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot, TickerSnapshot


def test_freshness_accepts_recent_data() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    result = check_freshness(now - timedelta(milliseconds=500), max_age_ms=1000, now=now)

    assert result.status == FreshnessStatus.FRESH
    assert result.is_fresh is True


def test_freshness_rejects_stale_data() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    result = check_freshness(now - timedelta(milliseconds=1501), max_age_ms=1500, now=now)

    assert result.status == FreshnessStatus.STALE
    assert result.is_fresh is False
    assert result.reason


def test_latency_threshold() -> None:
    assert check_latency(100, max_latency_ms=750).passed is True
    assert check_latency(751, max_latency_ms=750).passed is False


def test_ticker_mid_and_orderbook_depth() -> None:
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    ticker = TickerSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=Decimal("99"),
        ask=Decimal("101"),
        observed_at=observed_at,
    )
    orderbook = OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(OrderBookLevel(price=Decimal("99"), quantity=Decimal("2")),),
        asks=(OrderBookLevel(price=Decimal("101"), quantity=Decimal("3")),),
        observed_at=observed_at,
    )

    assert ticker.mid == Decimal("100")
    assert orderbook.top_depth_quote() == Decimal("501")
