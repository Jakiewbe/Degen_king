"""Tests for the Binance public REST market-data client."""

from __future__ import annotations

import inspect
import urllib.parse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.binance_public_rest import (
    SPOT_BOOK_TICKER_PATH,
    SPOT_DEPTH_PATH,
    SPOT_EXCHANGE_INFO_PATH,
    USDM_BOOK_TICKER_PATH,
    USDM_DEPTH_PATH,
    USDM_EXCHANGE_INFO_PATH,
    USDM_PREMIUM_INDEX_PATH,
    BinancePublicRestClient,
    BinancePublicRestConfig,
    BinancePublicRestError,
)


class FakeTransport:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout_seconds: float) -> Any:
        self.calls.append((url, timeout_seconds))
        path = urllib.parse.urlparse(url).path
        if path not in self.responses:
            raise AssertionError(f"Unexpected URL path: {path}")
        return self.responses[path]

    def parsed_calls(self) -> list[urllib.parse.ParseResult]:
        return [urllib.parse.urlparse(url) for url, _ in self.calls]


SPOT_BOOK_TICKER = {
    "symbol": "BTCUSDT",
    "bidPrice": "50000.00",
    "askPrice": "50001.00",
}

USDM_BOOK_TICKER = {
    "symbol": "BTCUSDT",
    "bidPrice": "50002.00",
    "askPrice": "50003.00",
}

USDM_PREMIUM_INDEX = {
    "symbol": "BTCUSDT",
    "markPrice": "50002.50",
    "indexPrice": "49990.00",
    "lastFundingRate": "0.00010000",
    "nextFundingTime": 1700000000000,
}

DEPTH = {
    "lastUpdateId": 1027024,
    "bids": [["50000.00", "1.50000000"]],
    "asks": [["50001.00", "2.00000000"]],
}

SPOT_EXCHANGE_INFO = {
    "symbols": [
        {
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
    ]
}

USDM_EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5.00"},
            ],
        }
    ]
}


def _client(
    responses: dict[str, Any] | None = None,
    *,
    config: BinancePublicRestConfig | None = None,
) -> tuple[BinancePublicRestClient, FakeTransport]:
    transport = FakeTransport(
        responses
        or {
            SPOT_BOOK_TICKER_PATH: SPOT_BOOK_TICKER,
            USDM_BOOK_TICKER_PATH: USDM_BOOK_TICKER,
            USDM_PREMIUM_INDEX_PATH: USDM_PREMIUM_INDEX,
            SPOT_DEPTH_PATH: DEPTH,
            USDM_DEPTH_PATH: DEPTH,
            SPOT_EXCHANGE_INFO_PATH: SPOT_EXCHANGE_INFO,
            USDM_EXCHANGE_INFO_PATH: USDM_EXCHANGE_INFO,
        }
    )
    return BinancePublicRestClient(config=config, transport=transport), transport


def _query(call: urllib.parse.ParseResult) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(call.query)


def test_config_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        BinancePublicRestConfig(timeout_seconds=0)


def test_config_rejects_non_positive_depth_limit() -> None:
    with pytest.raises(ValueError, match="depth_limit"):
        BinancePublicRestConfig(depth_limit=0)


def test_fetch_spot_ticker_uses_public_book_ticker_endpoint() -> None:
    client, transport = _client()

    ticker = client.fetch_spot_ticker("btcusdt")

    assert ticker.symbol == "BTCUSDT"
    assert ticker.market_type == MarketType.SPOT
    assert ticker.bid == Decimal("50000.00")
    assert ticker.ask == Decimal("50001.00")
    assert len(transport.calls) == 1
    call = transport.parsed_calls()[0]
    assert call.path == SPOT_BOOK_TICKER_PATH
    assert _query(call) == {"symbol": ["BTCUSDT"]}


def test_fetch_perp_ticker_merges_book_ticker_and_premium_index() -> None:
    client, transport = _client()

    ticker = client.fetch_perp_ticker("BTCUSDT")

    assert ticker.symbol == "BTCUSDT"
    assert ticker.market_type == MarketType.PERPETUAL
    assert ticker.bid == Decimal("50002.00")
    assert ticker.ask == Decimal("50003.00")
    assert ticker.mark == Decimal("50002.50")
    assert ticker.index == Decimal("49990.00")
    paths = [call.path for call in transport.parsed_calls()]
    assert paths == [USDM_BOOK_TICKER_PATH, USDM_PREMIUM_INDEX_PATH]


def test_fetch_spot_orderbook_uses_configured_depth_limit() -> None:
    config = BinancePublicRestConfig(depth_limit=50, timeout_seconds=2.5)
    client, transport = _client(config=config)

    book = client.fetch_spot_orderbook("BTCUSDT")

    assert book.symbol == "BTCUSDT"
    assert book.market_type == MarketType.SPOT
    assert book.checksum == "1027024"
    assert book.bids[0].price == Decimal("50000.00")
    call, timeout = transport.calls[0]
    parsed = urllib.parse.urlparse(call)
    assert parsed.path == SPOT_DEPTH_PATH
    assert _query(parsed) == {"symbol": ["BTCUSDT"], "limit": ["50"]}
    assert timeout == 2.5


def test_fetch_perp_orderbook_uses_futures_depth_endpoint() -> None:
    client, transport = _client()

    book = client.fetch_perp_orderbook("BTCUSDT")

    assert book.symbol == "BTCUSDT"
    assert book.market_type == MarketType.PERPETUAL
    assert transport.parsed_calls()[0].path == USDM_DEPTH_PATH


def test_fetch_funding_rate_uses_premium_index_payload() -> None:
    client, transport = _client()

    funding = client.fetch_funding_rate("BTCUSDT")

    assert funding.symbol == "BTCUSDT"
    assert funding.funding_rate == Decimal("0.00010000")
    assert funding.funding_interval_seconds == 8 * 3600
    assert funding.next_funding_time == datetime.fromtimestamp(1700000000000 / 1000, tz=UTC)
    assert transport.parsed_calls()[0].path == USDM_PREMIUM_INDEX_PATH


def test_fetch_spot_instrument_filters_exchange_info_by_symbol() -> None:
    client, transport = _client()

    instrument = client.fetch_spot_instrument("BTCUSDT")

    assert instrument.symbol == "BTCUSDT"
    assert instrument.market_type == MarketType.SPOT
    assert instrument.price_tick_size == Decimal("0.01000000")
    assert instrument.min_notional == Decimal("10.00000000")
    call = transport.parsed_calls()[0]
    assert call.path == SPOT_EXCHANGE_INFO_PATH
    assert _query(call) == {"symbol": ["BTCUSDT"]}


def test_fetch_perp_instrument_reads_public_futures_exchange_info() -> None:
    client, transport = _client()

    instrument = client.fetch_perp_instrument("BTCUSDT")

    assert instrument.symbol == "BTCUSDT"
    assert instrument.market_type == MarketType.PERPETUAL
    assert instrument.quantity_step_size == Decimal("0.001")
    assert instrument.min_notional == Decimal("5.00")
    assert transport.parsed_calls()[0].path == USDM_EXCHANGE_INFO_PATH


def test_fetch_symbol_market_data_returns_required_public_inputs() -> None:
    client, transport = _client()

    result = client.fetch_symbol_market_data("BTCUSDT")

    assert result["symbol"] == "BTCUSDT"
    assert result["spot_ticker"].market_type == MarketType.SPOT
    assert result["perp_ticker"].market_type == MarketType.PERPETUAL
    assert result["spot_orderbook"].market_type == MarketType.SPOT
    assert result["perp_orderbook"].market_type == MarketType.PERPETUAL
    assert result["funding"].symbol == "BTCUSDT"
    assert result["spot_instrument"].market_type == MarketType.SPOT
    assert result["perp_instrument"].market_type == MarketType.PERPETUAL
    assert "observed_at" in result
    assert [call.path for call in transport.parsed_calls()] == [
        SPOT_BOOK_TICKER_PATH,
        USDM_BOOK_TICKER_PATH,
        USDM_PREMIUM_INDEX_PATH,
        SPOT_DEPTH_PATH,
        USDM_DEPTH_PATH,
        USDM_PREMIUM_INDEX_PATH,
        SPOT_EXCHANGE_INFO_PATH,
        USDM_EXCHANGE_INFO_PATH,
    ]


def test_empty_symbol_is_rejected_before_transport_call() -> None:
    client, transport = _client()

    with pytest.raises(ValueError, match="symbol"):
        client.fetch_spot_ticker(" ")

    assert transport.calls == []


def test_mapping_payload_required_for_single_object_endpoints() -> None:
    client, _ = _client({SPOT_BOOK_TICKER_PATH: []})

    with pytest.raises(BinancePublicRestError, match="spot bookTicker"):
        client.fetch_spot_ticker("BTCUSDT")


def test_exchange_info_symbols_must_be_a_list() -> None:
    client, _ = _client({SPOT_EXCHANGE_INFO_PATH: {"symbols": {}}})

    with pytest.raises(BinancePublicRestError, match="symbols"):
        client.fetch_spot_instrument("BTCUSDT")


def test_exchange_info_missing_symbol_raises_client_error() -> None:
    client, _ = _client({USDM_EXCHANGE_INFO_PATH: {"symbols": []}})

    with pytest.raises(BinancePublicRestError, match="BTCUSDT"):
        client.fetch_perp_instrument("BTCUSDT")


def test_client_constructor_has_no_credential_parameters() -> None:
    signature = inspect.signature(BinancePublicRestClient)

    assert "config" in signature.parameters
    assert "transport" in signature.parameters
    assert len(signature.parameters) == 2


def test_module_contains_no_private_or_trading_endpoint_literals() -> None:
    source = Path("src/degenking/market_data/binance_public_rest.py").read_text()

    forbidden_literals = (
        "X-MBX-" + "APIKEY",
        "signature",
        "/api/v3/" + "account",
        "/api/v3/" + "order",
        "/fapi/v1/" + "order",
        "/fapi/v2/" + "account",
        "/fapi/v2/" + "positionRisk",
    )
    for literal in forbidden_literals:
        assert literal not in source
