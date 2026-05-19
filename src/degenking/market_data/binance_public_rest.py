"""Binance public REST client for read-only market data.

This module deliberately supports public market-data endpoints only. It does
not accept credentials, sign authenticated calls, fetch account state, or submit orders.
Unit tests inject a fake transport, so tests do not perform network I/O.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from degenking.common.time import utc_now
from degenking.market_data.binance_readonly import (
    normalize_funding_rate,
    normalize_perp_orderbook,
    normalize_perp_ticker,
    normalize_spot_exchange_info_symbol,
    normalize_spot_orderbook,
    normalize_spot_ticker,
    normalize_usdm_exchange_info_symbol,
)
from degenking.market_data.models import (
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookSnapshot,
    TickerSnapshot,
)

JsonPayload = Mapping[str, Any] | Sequence[Any]
JsonTransport = Callable[[str, float], JsonPayload]

DEFAULT_SPOT_BASE_URL = "https://api.binance.com"
DEFAULT_USDM_BASE_URL = "https://fapi.binance.com"

SPOT_BOOK_TICKER_PATH = "/api/v3/ticker/bookTicker"
SPOT_DEPTH_PATH = "/api/v3/depth"
SPOT_EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"
USDM_BOOK_TICKER_PATH = "/fapi/v1/ticker/bookTicker"
USDM_DEPTH_PATH = "/fapi/v1/depth"
USDM_PREMIUM_INDEX_PATH = "/fapi/v1/premiumIndex"
USDM_EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"


@dataclass(frozen=True, slots=True)
class BinancePublicRestConfig:
    """Configuration for Binance public REST reads."""

    spot_base_url: str = DEFAULT_SPOT_BASE_URL
    usdm_base_url: str = DEFAULT_USDM_BASE_URL
    timeout_seconds: float = 5.0
    depth_limit: int = 100

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.depth_limit <= 0:
            raise ValueError("depth_limit must be positive")


class BinancePublicRestError(RuntimeError):
    """Raised when Binance public REST payloads are malformed for this client."""


class BinancePublicRestClient:
    """Small read-only Binance public REST client.

    The client has no credential fields by design. Callers can inject
    ``transport`` to test URL construction and payload handling without network
    access.
    """

    def __init__(
        self,
        *,
        config: BinancePublicRestConfig | None = None,
        transport: JsonTransport | None = None,
    ) -> None:
        self._config = config or BinancePublicRestConfig()
        self._transport = transport or _default_json_transport

    @property
    def config(self) -> BinancePublicRestConfig:
        return self._config

    def fetch_spot_ticker(self, symbol: str) -> TickerSnapshot:
        payload = self._get_spot(SPOT_BOOK_TICKER_PATH, {"symbol": _symbol(symbol)})
        return normalize_spot_ticker(_require_mapping(payload, "spot bookTicker"))

    def fetch_perp_ticker(self, symbol: str) -> TickerSnapshot:
        resolved_symbol = _symbol(symbol)
        book_payload = self._get_usdm(
            USDM_BOOK_TICKER_PATH,
            {"symbol": resolved_symbol},
        )
        premium_payload = self._get_usdm(
            USDM_PREMIUM_INDEX_PATH,
            {"symbol": resolved_symbol},
        )
        merged = {
            **_require_mapping(book_payload, "USD-M bookTicker"),
            **_require_mapping(premium_payload, "USD-M premiumIndex"),
        }
        return normalize_perp_ticker(merged)

    def fetch_spot_orderbook(self, symbol: str) -> OrderBookSnapshot:
        resolved_symbol = _symbol(symbol)
        payload = self._get_spot(
            SPOT_DEPTH_PATH,
            {"symbol": resolved_symbol, "limit": self._config.depth_limit},
        )
        return normalize_spot_orderbook(
            _require_mapping(payload, "spot depth"),
            symbol=resolved_symbol,
        )

    def fetch_perp_orderbook(self, symbol: str) -> OrderBookSnapshot:
        resolved_symbol = _symbol(symbol)
        payload = self._get_usdm(
            USDM_DEPTH_PATH,
            {"symbol": resolved_symbol, "limit": self._config.depth_limit},
        )
        return normalize_perp_orderbook(
            _require_mapping(payload, "USD-M depth"),
            symbol=resolved_symbol,
        )

    def fetch_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        resolved_symbol = _symbol(symbol)
        payload = self._get_usdm(
            USDM_PREMIUM_INDEX_PATH,
            {"symbol": resolved_symbol},
        )
        return normalize_funding_rate(_require_mapping(payload, "USD-M premiumIndex"))

    def fetch_spot_instrument(self, symbol: str) -> InstrumentInfo:
        resolved_symbol = _symbol(symbol)
        payload = self._get_spot(
            SPOT_EXCHANGE_INFO_PATH,
            {"symbol": resolved_symbol},
        )
        entry = _find_symbol_entry(payload, symbol=resolved_symbol, label="spot exchangeInfo")
        return normalize_spot_exchange_info_symbol(entry)

    def fetch_perp_instrument(self, symbol: str) -> InstrumentInfo:
        resolved_symbol = _symbol(symbol)
        payload = self._get_usdm(USDM_EXCHANGE_INFO_PATH, {})
        entry = _find_symbol_entry(payload, symbol=resolved_symbol, label="USD-M exchangeInfo")
        return normalize_usdm_exchange_info_symbol(entry)

    def fetch_symbol_market_data(self, symbol: str) -> dict[str, object]:
        """Fetch the public inputs required by the paper funding-arb path."""

        resolved_symbol = _symbol(symbol)
        return {
            "symbol": resolved_symbol,
            "spot_ticker": self.fetch_spot_ticker(resolved_symbol),
            "perp_ticker": self.fetch_perp_ticker(resolved_symbol),
            "spot_orderbook": self.fetch_spot_orderbook(resolved_symbol),
            "perp_orderbook": self.fetch_perp_orderbook(resolved_symbol),
            "funding": self.fetch_funding_rate(resolved_symbol),
            "spot_instrument": self.fetch_spot_instrument(resolved_symbol),
            "perp_instrument": self.fetch_perp_instrument(resolved_symbol),
            "observed_at": utc_now(),
        }

    def _get_spot(self, path: str, params: Mapping[str, object]) -> JsonPayload:
        return self._get(self._config.spot_base_url, path, params)

    def _get_usdm(self, path: str, params: Mapping[str, object]) -> JsonPayload:
        return self._get(self._config.usdm_base_url, path, params)

    def _get(
        self,
        base_url: str,
        path: str,
        params: Mapping[str, object],
    ) -> JsonPayload:
        url = _build_url(base_url, path, params)
        return self._transport(url, self._config.timeout_seconds)


def _default_json_transport(url: str, timeout_seconds: float) -> JsonPayload:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "degenking-monitor/0.1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, (dict, list)):
        raise BinancePublicRestError(
            f"Expected JSON object or array from Binance public REST, got {type(payload).__name__}"
        )
    return payload


def _build_url(base_url: str, path: str, params: Mapping[str, object]) -> str:
    if not base_url:
        raise ValueError("base_url must not be empty")
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")

    clean_base = base_url.rstrip("/")
    query = urllib.parse.urlencode(
        {key: str(value) for key, value in params.items() if value is not None}
    )
    if not query:
        return f"{clean_base}{path}"
    return f"{clean_base}{path}?{query}"


def _symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _require_mapping(payload: JsonPayload, label: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BinancePublicRestError(
            f"Expected {label} payload to be an object, got {type(payload).__name__}"
        )
    return dict(payload)


def _find_symbol_entry(payload: JsonPayload, *, symbol: str, label: str) -> dict[str, Any]:
    data = _require_mapping(payload, label)
    symbols = data.get("symbols")
    if not isinstance(symbols, list):
        raise BinancePublicRestError(
            f"Expected {label} payload field 'symbols' to be a list"
        )
    for entry in symbols:
        if isinstance(entry, Mapping) and entry.get("symbol") == symbol:
            return dict(entry)
    raise BinancePublicRestError(f"{label} did not contain symbol {symbol}")


__all__ = [
    "BinancePublicRestClient",
    "BinancePublicRestConfig",
    "BinancePublicRestError",
    "DEFAULT_SPOT_BASE_URL",
    "DEFAULT_USDM_BASE_URL",
    "SPOT_BOOK_TICKER_PATH",
    "SPOT_DEPTH_PATH",
    "SPOT_EXCHANGE_INFO_PATH",
    "USDM_BOOK_TICKER_PATH",
    "USDM_DEPTH_PATH",
    "USDM_EXCHANGE_INFO_PATH",
    "USDM_PREMIUM_INDEX_PATH",
]
