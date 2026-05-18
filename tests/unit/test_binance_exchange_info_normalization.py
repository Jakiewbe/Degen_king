"""Tests for Binance exchangeInfo instrument normalization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.binance_readonly import (
    normalize_spot_exchange_info_symbol,
    normalize_usdm_exchange_info_symbol,
)
from degenking.market_data.models import InstrumentInfo

# ---------------------------------------------------------------------------
# Spot exchangeInfo fixtures
# ---------------------------------------------------------------------------

SPOT_SYMBOL_FULL = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {
            "filterType": "LOT_SIZE",
            "stepSize": "0.00001000",
            "minQty": "0.00001000",
        },
        {"filterType": "NOTIONAL", "minNotional": "10.00000000"},
    ],
}

SPOT_SYMBOL_NO_MIN_NOTIONAL = {
    "symbol": "ETHUSDT",
    "baseAsset": "ETH",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {
            "filterType": "LOT_SIZE",
            "stepSize": "0.00010000",
            "minQty": "0.00010000",
        },
    ],
}

SPOT_SYMBOL_NO_MIN_QTY = {
    "symbol": "BNBUSDT",
    "baseAsset": "BNB",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.10000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.01000000"},
        {"filterType": "NOTIONAL", "minNotional": "10.00000000"},
    ],
}

SPOT_SYMBOL_LEGACY_MIN_NOTIONAL = {
    "symbol": "SOLUSDT",
    "baseAsset": "SOL",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {
            "filterType": "LOT_SIZE",
            "stepSize": "0.01000000",
            "minQty": "0.01000000",
        },
        {"filterType": "MIN_NOTIONAL", "minNotional": "5.00000000"},
    ],
}


# ---------------------------------------------------------------------------
# USD-M futures exchangeInfo fixtures
# ---------------------------------------------------------------------------

USDM_SYMBOL_FULL = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
        {"filterType": "MIN_NOTIONAL", "notional": "5.00"},
    ],
}

USDM_SYMBOL_NO_MIN_NOTIONAL = {
    "symbol": "ETHUSDT",
    "baseAsset": "ETH",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
    ],
}

USDM_SYMBOL_NOTIONAL_MIN_NOTIONAL_KEY = {
    "symbol": "SOLUSDT",
    "baseAsset": "SOL",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.001"},
        {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01"},
        {"filterType": "MIN_NOTIONAL", "minNotional": "5.00"},
    ],
}


# ---------------------------------------------------------------------------
# Spot normalizer tests
# ---------------------------------------------------------------------------


def test_normalize_spot_exchange_info_basic() -> None:
    result = normalize_spot_exchange_info_symbol(SPOT_SYMBOL_FULL)

    assert isinstance(result, InstrumentInfo)
    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.SPOT
    assert result.base_asset == "BTC"
    assert result.quote_asset == "USDT"
    assert result.price_tick_size == Decimal("0.01000000")
    assert result.quantity_step_size == Decimal("0.00001000")
    assert result.min_quantity == Decimal("0.00001000")
    assert result.min_notional == Decimal("10.00000000")


def test_normalize_spot_exchange_info_no_min_notional() -> None:
    result = normalize_spot_exchange_info_symbol(SPOT_SYMBOL_NO_MIN_NOTIONAL)

    assert result.symbol == "ETHUSDT"
    assert result.min_quantity == Decimal("0.00010000")
    assert result.min_notional is None


def test_normalize_spot_exchange_info_no_min_qty() -> None:
    result = normalize_spot_exchange_info_symbol(SPOT_SYMBOL_NO_MIN_QTY)

    assert result.symbol == "BNBUSDT"
    assert result.min_quantity is None
    assert result.min_notional == Decimal("10.00000000")


def test_normalize_spot_exchange_info_legacy_min_notional() -> None:
    result = normalize_spot_exchange_info_symbol(SPOT_SYMBOL_LEGACY_MIN_NOTIONAL)

    assert result.symbol == "SOLUSDT"
    assert result.min_notional == Decimal("5.00000000")


def test_normalize_spot_exchange_info_market_type_is_spot() -> None:
    result = normalize_spot_exchange_info_symbol(SPOT_SYMBOL_FULL)
    assert result.market_type == MarketType.SPOT


# ---------------------------------------------------------------------------
# USD-M normalizer tests
# ---------------------------------------------------------------------------


def test_normalize_usdm_exchange_info_basic() -> None:
    result = normalize_usdm_exchange_info_symbol(USDM_SYMBOL_FULL)

    assert isinstance(result, InstrumentInfo)
    assert result.exchange == "binance"
    assert result.symbol == "BTCUSDT"
    assert result.market_type == MarketType.PERPETUAL
    assert result.base_asset == "BTC"
    assert result.quote_asset == "USDT"
    assert result.price_tick_size == Decimal("0.10")
    assert result.quantity_step_size == Decimal("0.001")
    assert result.min_quantity == Decimal("0.001")
    assert result.min_notional == Decimal("5.00")


def test_normalize_usdm_exchange_info_no_min_notional() -> None:
    result = normalize_usdm_exchange_info_symbol(USDM_SYMBOL_NO_MIN_NOTIONAL)

    assert result.symbol == "ETHUSDT"
    assert result.market_type == MarketType.PERPETUAL
    assert result.min_notional is None


def test_normalize_usdm_exchange_info_notional_min_notional_key() -> None:
    """MIN_NOTIONAL filter may use 'minNotional' instead of 'notional'."""
    result = normalize_usdm_exchange_info_symbol(USDM_SYMBOL_NOTIONAL_MIN_NOTIONAL_KEY)

    assert result.symbol == "SOLUSDT"
    assert result.min_notional == Decimal("5.00")


def test_normalize_usdm_exchange_info_market_type_is_perpetual() -> None:
    result = normalize_usdm_exchange_info_symbol(USDM_SYMBOL_FULL)
    assert result.market_type == MarketType.PERPETUAL


# ---------------------------------------------------------------------------
# Error cases — missing top-level fields
# ---------------------------------------------------------------------------


def test_missing_symbol_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'symbol'"):
        normalize_spot_exchange_info_symbol(
            {"baseAsset": "BTC", "quoteAsset": "USDT", "filters": []}
        )


def test_missing_base_asset_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'baseAsset'"):
        normalize_spot_exchange_info_symbol(
            {"symbol": "BTCUSDT", "quoteAsset": "USDT", "filters": []}
        )


def test_missing_quote_asset_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required field: 'quoteAsset'"):
        normalize_spot_exchange_info_symbol(
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "filters": []}
        )


# ---------------------------------------------------------------------------
# Error cases — missing filters
# ---------------------------------------------------------------------------


def test_missing_price_filter_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required filter: 'PRICE_FILTER'"):
        normalize_spot_exchange_info_symbol(
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                ],
            }
        )


def test_missing_lot_size_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required filter: 'LOT_SIZE'"):
        normalize_spot_exchange_info_symbol(
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                ],
            }
        )


def test_filters_not_list_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Expected 'filters' to be a list"):
        normalize_spot_exchange_info_symbol(
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": "not-a-list",
            }
        )


# ---------------------------------------------------------------------------
# Error cases — malformed numeric fields
# ---------------------------------------------------------------------------


def test_malformed_tick_size_raises_value_error() -> None:
    with pytest.raises(ValueError, match="'tickSize'"):
        normalize_spot_exchange_info_symbol(
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "abc"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                ],
            }
        )


def test_malformed_step_size_raises_value_error() -> None:
    with pytest.raises(ValueError, match="'stepSize'"):
        normalize_usdm_exchange_info_symbol(
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "stepSize": "xyz"},
                ],
            }
        )


# ---------------------------------------------------------------------------
# Decimal precision
# ---------------------------------------------------------------------------


def test_numeric_filter_values_not_strings() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": 0.01},
            {"filterType": "LOT_SIZE", "stepSize": 1e-6, "minQty": 1e-6},
        ],
    }
    result = normalize_spot_exchange_info_symbol(payload)
    assert result.price_tick_size == Decimal("0.01")
    assert result.quantity_step_size == Decimal("0.000001")
    assert result.min_quantity == Decimal("0.000001")
