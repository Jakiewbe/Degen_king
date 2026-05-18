"""Tests for Binance read-only normalization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.binance_readonly import (
    normalize_funding_rate,
    normalize_orderbook,
    normalize_perp_orderbook,
    normalize_perp_ticker,
    normalize_spot_orderbook,
    normalize_spot_ticker,
)
from degenking.market_data.models import (
    FundingRateSnapshot,
    OrderBookSnapshot,
    TickerSnapshot,
)

FROZEN_TIME = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Spot ticker fixtures
# ---------------------------------------------------------------------------

SPOT_TICKER_VALID = {
    "symbol": "BTCUSDT",
    "bidPrice": "50000.00",
    "bidQty": "1.50000000",
    "askPrice": "50001.00",
    "askQty": "2.00000000",
}


def test_normalize_spot_ticker_basic() -> None:
    result = normalize_spot_ticker(SPOT_TICKER_VALID, observed_at=FROZEN_TIME)

    assert isinstance(result, TickerSnapshot)
    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.SPOT
    assert result.bid == Decimal("50000.00")
    assert result.ask == Decimal("50001.00")
    assert result.mark is None
    assert result.index is None
    assert result.mid == Decimal("50000.50")
    assert result.observed_at == FROZEN_TIME


def test_normalize_spot_ticker_default_observed_at() -> None:
    result = normalize_spot_ticker(SPOT_TICKER_VALID)
    assert result.observed_at is not None
    assert result.observed_at.tzinfo == UTC


def test_normalize_spot_ticker_different_symbol() -> None:
    payload = {
        "symbol": "ETHUSDT",
        "bidPrice": "3000.00",
        "askPrice": "3001.00",
    }
    result = normalize_spot_ticker(payload, observed_at=FROZEN_TIME)
    assert result.symbol == "ETHUSDT"
    assert result.bid == Decimal("3000.00")
    assert result.ask == Decimal("3001.00")


def test_normalize_spot_ticker_missing_symbol() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'symbol'"):
        normalize_spot_ticker({"bidPrice": "1", "askPrice": "2"})


def test_normalize_spot_ticker_missing_bid() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'bidPrice'"):
        normalize_spot_ticker({"symbol": "BTCUSDT", "askPrice": "2"})


def test_normalize_spot_ticker_missing_ask() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'askPrice'"):
        normalize_spot_ticker({"symbol": "BTCUSDT", "bidPrice": "1"})


# ---------------------------------------------------------------------------
# Perp ticker fixtures
# ---------------------------------------------------------------------------

PERP_TICKER_FULL = {
    "symbol": "BTCUSDT",
    "bidPrice": "50000.00",
    "askPrice": "50001.00",
    "markPrice": "50000.50",
    "indexPrice": "49990.00",
}

PERP_TICKER_NO_MARK_INDEX = {
    "symbol": "ETHUSDT",
    "bidPrice": "3000.00",
    "askPrice": "3001.00",
}


def test_normalize_perp_ticker_with_mark_index() -> None:
    result = normalize_perp_ticker(PERP_TICKER_FULL, observed_at=FROZEN_TIME)

    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.PERPETUAL
    assert result.bid == Decimal("50000.00")
    assert result.ask == Decimal("50001.00")
    assert result.mark == Decimal("50000.50")
    assert result.index == Decimal("49990.00")
    assert result.observed_at == FROZEN_TIME


def test_normalize_perp_ticker_without_mark_index() -> None:
    result = normalize_perp_ticker(PERP_TICKER_NO_MARK_INDEX, observed_at=FROZEN_TIME)

    assert result.market_type == MarketType.PERPETUAL
    assert result.mark is None
    assert result.index is None
    assert result.bid == Decimal("3000.00")
    assert result.ask == Decimal("3001.00")


def test_normalize_perp_ticker_missing_bid() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'bidPrice'"):
        normalize_perp_ticker({"symbol": "BTCUSDT", "askPrice": "2"})


# ---------------------------------------------------------------------------
# Orderbook fixtures
# ---------------------------------------------------------------------------

ORDERBOOK_VALID = {
    "symbol": "BTCUSDT",
    "lastUpdateId": 1027024,
    "bids": [["50000.00", "1.50000000"], ["49999.00", "2.00000000"]],
    "asks": [["50001.00", "1.50000000"], ["50002.00", "3.00000000"]],
}

ORDERBOOK_EMPTY_LEVELS = {
    "symbol": "BTCUSDT",
    "lastUpdateId": 1,
    "bids": [],
    "asks": [],
}


def test_normalize_orderbook_basic() -> None:
    result = normalize_orderbook(ORDERBOOK_VALID, observed_at=FROZEN_TIME)

    assert isinstance(result, OrderBookSnapshot)
    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.SPOT
    assert result.checksum == "1027024"
    assert result.observed_at == FROZEN_TIME

    assert len(result.bids) == 2
    assert result.bids[0].price == Decimal("50000.00")
    assert result.bids[0].quantity == Decimal("1.50000000")
    assert result.bids[1].price == Decimal("49999.00")
    assert result.bids[1].quantity == Decimal("2.00000000")

    assert len(result.asks) == 2
    assert result.asks[0].price == Decimal("50001.00")
    assert result.asks[0].quantity == Decimal("1.50000000")
    assert result.asks[1].price == Decimal("50002.00")
    assert result.asks[1].quantity == Decimal("3.00000000")


def test_normalize_orderbook_empty_levels() -> None:
    result = normalize_orderbook(ORDERBOOK_EMPTY_LEVELS, observed_at=FROZEN_TIME)
    assert len(result.bids) == 0
    assert len(result.asks) == 0


def test_normalize_orderbook_no_checksum() -> None:
    payload = {"symbol": "BTCUSDT", "bids": [], "asks": []}
    result = normalize_orderbook(payload, observed_at=FROZEN_TIME)
    assert result.checksum is None


def test_normalize_orderbook_accepts_external_symbol() -> None:
    payload = {
        "lastUpdateId": 1027024,
        "bids": [["50000.00", "1.50000000"]],
        "asks": [["50001.00", "1.50000000"]],
    }
    result = normalize_spot_orderbook(
        payload,
        symbol="BTCUSDT",
        observed_at=FROZEN_TIME,
    )

    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.SPOT


def test_normalize_perp_orderbook_uses_futures_market_type_and_event_time() -> None:
    payload = {
        "lastUpdateId": 1027024,
        "E": 1700000000000,
        "T": 1699999999999,
        "bids": [["50000.00", "1.50000000"]],
        "asks": [["50001.00", "1.50000000"]],
    }
    result = normalize_perp_orderbook(payload, symbol="BTCUSDT")

    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.PERPETUAL
    assert result.observed_at == datetime.fromtimestamp(1700000000000 / 1000, tz=UTC)


def test_normalize_orderbook_missing_symbol() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'symbol'"):
        normalize_orderbook({"bids": [], "asks": []})


def test_normalize_orderbook_missing_bids() -> None:
    with pytest.raises(ValueError, match="Expected 'bids' to be a list"):
        normalize_orderbook({"symbol": "BTCUSDT", "asks": []})


def test_normalize_orderbook_missing_asks() -> None:
    with pytest.raises(ValueError, match="Expected 'asks' to be a list"):
        normalize_orderbook({"symbol": "BTCUSDT", "bids": []})


def test_normalize_orderbook_bids_not_list() -> None:
    with pytest.raises(ValueError, match="Expected 'bids' to be a list"):
        normalize_orderbook({"symbol": "BTCUSDT", "bids": "invalid", "asks": []})


def test_normalize_orderbook_malformed_level() -> None:
    with pytest.raises(ValueError, match="Orderbook entry 0 must be"):
        normalize_orderbook(
            {"symbol": "BTCUSDT", "bids": [["50000.00"]], "asks": []}
        )


def test_normalize_orderbook_top_depth_quote() -> None:
    result = normalize_orderbook(ORDERBOOK_VALID, observed_at=FROZEN_TIME)
    # bid depth: 50000*1.5 + 49999*2 = 75000 + 99998 = 174998
    # ask depth: 50001*1.5 + 50002*3 = 75001.5 + 150006 = 225007.5
    # total = 400005.5
    depth = result.top_depth_quote(levels=10)
    assert depth == Decimal("400005.5")


# ---------------------------------------------------------------------------
# Funding rate fixtures
# ---------------------------------------------------------------------------

FUNDING_VALID = {
    "symbol": "BTCUSDT",
    "lastFundingRate": "0.00010000",
    "nextFundingTime": 1700000000000,
    "fundingIntervalHours": 8,
}

FUNDING_SOL = {
    "symbol": "SOLUSDT",
    "lastFundingRate": "0.00020000",
    "nextFundingTime": 1700006400000,
    "fundingIntervalHours": 4,
}


def test_normalize_funding_rate_basic() -> None:
    result = normalize_funding_rate(FUNDING_VALID, observed_at=FROZEN_TIME)

    assert isinstance(result, FundingRateSnapshot)
    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.funding_rate == Decimal("0.00010000")
    assert result.funding_interval_seconds == 8 * 3600
    assert result.observed_at == FROZEN_TIME

    expected_next = datetime.fromtimestamp(1700000000000 / 1000, tz=UTC)
    assert result.next_funding_time == expected_next


def test_normalize_funding_rate_sol_4h_interval() -> None:
    result = normalize_funding_rate(FUNDING_SOL, observed_at=FROZEN_TIME)
    assert result.symbol == "SOLUSDT"
    assert result.funding_rate == Decimal("0.00020000")
    assert result.funding_interval_seconds == 4 * 3600


def test_normalize_funding_rate_negative() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "lastFundingRate": "-0.00005000",
        "nextFundingTime": 1700000000000,
        "fundingIntervalHours": 8,
    }
    result = normalize_funding_rate(payload, observed_at=FROZEN_TIME)
    assert result.funding_rate == Decimal("-0.00005000")


def test_normalize_funding_rate_missing_symbol() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'symbol'"):
        normalize_funding_rate(
            {
                "lastFundingRate": "0.0001",
                "nextFundingTime": 1,
                "fundingIntervalHours": 8,
            }
        )


def test_normalize_funding_rate_missing_funding_rate() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'lastFundingRate'"):
        normalize_funding_rate(
            {"symbol": "BTCUSDT", "nextFundingTime": 1, "fundingIntervalHours": 8}
        )


def test_normalize_funding_rate_missing_next_funding_time() -> None:
    with pytest.raises(ValueError, match="nextFundingTime"):
        normalize_funding_rate(
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "fundingIntervalHours": 8,
            }
        )


def test_normalize_funding_rate_defaults_interval_to_8h() -> None:
    result = normalize_funding_rate(
        {
            "symbol": "BTCUSDT",
            "lastFundingRate": "0.0001",
            "nextFundingTime": 1700000000000,
        },
        observed_at=FROZEN_TIME,
    )

    assert result.funding_interval_seconds == 8 * 3600


def test_normalize_funding_rate_bad_interval_type() -> None:
    with pytest.raises(ValueError, match="fundingIntervalHours"):
        normalize_funding_rate(
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 1700000000000,
                "fundingIntervalHours": "eight",
            }
        )


def test_normalize_funding_rate_bad_timestamp_type() -> None:
    with pytest.raises(ValueError, match="nextFundingTime"):
        normalize_funding_rate(
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "nextFundingTime": "soon",
                "fundingIntervalHours": 8,
            }
        )


# ---------------------------------------------------------------------------
# Decimal precision edge cases
# ---------------------------------------------------------------------------


def test_normalize_spot_ticker_numeric_not_string() -> None:
    payload = {"symbol": "BTCUSDT", "bidPrice": 50000.0, "askPrice": 50001}
    result = normalize_spot_ticker(payload, observed_at=FROZEN_TIME)
    assert result.bid == Decimal("50000.0")
    assert result.ask == Decimal("50001")


def test_normalize_funding_rate_scientific_notation() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "lastFundingRate": "1e-4",
        "nextFundingTime": 1700000000000,
        "fundingIntervalHours": 8,
    }
    result = normalize_funding_rate(payload, observed_at=FROZEN_TIME)
    assert result.funding_rate == Decimal("0.0001")
