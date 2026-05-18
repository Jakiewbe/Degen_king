"""Pure normalization helpers for Binance testnet payloads.

No network calls. No credentials. No async. Deterministic parsing only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from degenking.common.enums import ExchangeName, MarketType
from degenking.common.money import decimal_from_number
from degenking.common.time import utc_now
from degenking.market_data.models import (
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)

_EXCHANGE = ExchangeName.BINANCE.value


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_ts_ms(value: object, *, field_name: str) -> datetime:
    """Parse a millisecond Unix timestamp into a timezone-aware UTC datetime."""
    if not isinstance(value, (int, float)):
        raise ValueError(
            f"Expected {field_name} to be a numeric Unix timestamp in milliseconds, "
            f"got {type(value).__name__}"
        )
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


def _require_str(data: dict, key: str) -> str:
    value = data.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {key!r}")
    if not isinstance(value, str):
        raise ValueError(f"Expected {key!r} to be str, got {type(value).__name__}")
    return value


def _resolve_symbol(data: dict, symbol: str | None) -> str:
    if symbol is not None:
        return symbol
    return _require_str(data, "symbol")


def _require_decimal(data: dict, key: str) -> Decimal:
    value = data.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {key!r}")
    try:
        return decimal_from_number(value)
    except Exception:
        raise ValueError(
            f"Expected {key!r} to be a numeric value, got {type(value).__name__}"
        ) from None


def _optional_decimal(data: dict, key: str) -> Decimal | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return decimal_from_number(value)
    except Exception:
        raise ValueError(
            f"Expected {key!r} to be a numeric value if present, "
            f"got {type(value).__name__}"
        ) from None


def _build_orderbook_levels(
    entries: list[list[str | float | int]],
) -> tuple[OrderBookLevel, ...]:
    levels: list[OrderBookLevel] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            raise ValueError(
                f"Orderbook entry {i} must be [price, quantity], got {entry!r}"
            )
        levels.append(
            OrderBookLevel(
                price=decimal_from_number(entry[0]),
                quantity=decimal_from_number(entry[1]),
            )
        )
    return tuple(levels)


# ---------------------------------------------------------------------------
# Public normalizers
# ---------------------------------------------------------------------------


def normalize_spot_ticker(
    data: dict,
    *,
    observed_at: datetime | None = None,
) -> TickerSnapshot:
    """Convert a Binance spot bookTicker payload into a TickerSnapshot.

    Required fields: ``symbol``, ``bidPrice``, ``askPrice``.

    Representative payload::

        {"symbol": "BTCUSDT", "bidPrice": "50000.00", "askPrice": "50001.00"}
    """
    symbol = _require_str(data, "symbol")
    bid = _require_decimal(data, "bidPrice")
    ask = _require_decimal(data, "askPrice")

    return TickerSnapshot(
        exchange=_EXCHANGE,
        symbol=symbol,
        market_type=MarketType.SPOT,
        bid=bid,
        ask=ask,
        observed_at=observed_at or utc_now(),
    )


def normalize_perp_ticker(
    data: dict,
    *,
    observed_at: datetime | None = None,
) -> TickerSnapshot:
    """Convert a Binance USD-M futures ticker into a TickerSnapshot.

    Uses bookTicker fields for bid/ask and premiumIndex fields for
    mark/index when present.

    Required fields: ``symbol``, ``bidPrice``, ``askPrice``.
    Optional fields: ``markPrice``, ``indexPrice``.

    Representative payload::

        {
            "symbol": "BTCUSDT",
            "bidPrice": "50000.00", "askPrice": "50001.00",
            "markPrice": "50000.50", "indexPrice": "49990.00"
        }
    """
    symbol = _require_str(data, "symbol")
    bid = _require_decimal(data, "bidPrice")
    ask = _require_decimal(data, "askPrice")
    mark = _optional_decimal(data, "markPrice")
    index = _optional_decimal(data, "indexPrice")

    return TickerSnapshot(
        exchange=_EXCHANGE,
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        bid=bid,
        ask=ask,
        mark=mark,
        index=index,
        observed_at=observed_at or utc_now(),
    )


def normalize_orderbook(
    data: dict,
    *,
    symbol: str | None = None,
    market_type: MarketType = MarketType.SPOT,
    observed_at: datetime | None = None,
) -> OrderBookSnapshot:
    """Convert a Binance depth payload into an OrderBookSnapshot.

    Required fields: ``bids``, ``asks``. ``symbol`` is accepted in the payload
    for test fixtures and adapters, but callers should pass ``symbol`` when
    normalizing real REST depth responses because Binance spot/futures depth
    responses do not include it.

    Optional fields: ``lastUpdateId`` (stored as checksum), ``E`` or ``T`` for
    futures event/transaction timestamps when ``observed_at`` is not supplied.
    """
    resolved_symbol = _resolve_symbol(data, symbol)

    bids_raw = data.get("bids")
    if bids_raw is None or not isinstance(bids_raw, list):
        raise ValueError(f"Expected 'bids' to be a list, got {type(bids_raw).__name__}")
    asks_raw = data.get("asks")
    if asks_raw is None or not isinstance(asks_raw, list):
        raise ValueError(f"Expected 'asks' to be a list, got {type(asks_raw).__name__}")

    last_update_id = data.get("lastUpdateId")
    checksum = str(last_update_id) if last_update_id is not None else None
    inferred_observed_at = observed_at or _optional_observed_at(data) or utc_now()

    return OrderBookSnapshot(
        exchange=_EXCHANGE,
        symbol=resolved_symbol,
        market_type=market_type,
        bids=_build_orderbook_levels(bids_raw),
        asks=_build_orderbook_levels(asks_raw),
        observed_at=inferred_observed_at,
        checksum=checksum,
    )


def _optional_observed_at(data: dict) -> datetime | None:
    for key in ("time", "E", "T"):
        if data.get(key) is not None:
            return _parse_ts_ms(data[key], field_name=key)
    return None


def normalize_spot_orderbook(
    data: dict,
    *,
    symbol: str | None = None,
    observed_at: datetime | None = None,
) -> OrderBookSnapshot:
    """Normalize a Binance spot depth payload."""

    return normalize_orderbook(
        data,
        symbol=symbol,
        market_type=MarketType.SPOT,
        observed_at=observed_at,
    )


def normalize_perp_orderbook(
    data: dict,
    *,
    symbol: str | None = None,
    observed_at: datetime | None = None,
) -> OrderBookSnapshot:
    """Normalize a Binance USD-M futures depth payload."""

    return normalize_orderbook(
        data,
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        observed_at=observed_at,
    )


def normalize_funding_rate(
    data: dict,
    *,
    observed_at: datetime | None = None,
) -> FundingRateSnapshot:
    """Convert a Binance funding rate payload into a FundingRateSnapshot.

    Required fields: ``symbol``, ``nextFundingTime``, and either
    ``fundingRate`` or Binance premiumIndex ``lastFundingRate``.

    ``nextFundingTime`` is a millisecond Unix timestamp.
    ``fundingIntervalHours`` may be merged from Binance ``/fapi/v1/fundingInfo``.
    It defaults to 8 hours when absent, which is Binance's standard interval for
    most USD-M contracts. Symbols with adjusted intervals should pass the
    fundingInfo value explicitly before strategy/risk evaluation.

    Representative payload::

        {
            "symbol": "BTCUSDT",
            "lastFundingRate": "0.00010000",
            "nextFundingTime": 1700000000000,
            "fundingIntervalHours": 8
        }
    """
    symbol = _require_str(data, "symbol")
    funding_rate = _optional_decimal(data, "fundingRate")
    if funding_rate is None:
        funding_rate = _require_decimal(data, "lastFundingRate")
    next_funding_ts = _parse_ts_ms(
        data.get("nextFundingTime"), field_name="nextFundingTime"
    )

    interval_raw = data.get("fundingIntervalHours", 8)
    try:
        funding_interval_hours = int(interval_raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"Expected 'fundingIntervalHours' to be an integer, "
            f"got {type(interval_raw).__name__}"
        ) from None
    if funding_interval_hours <= 0:
        raise ValueError("'fundingIntervalHours' must be positive")
    funding_interval_seconds = funding_interval_hours * 3600

    return FundingRateSnapshot(
        exchange=_EXCHANGE,
        symbol=symbol,
        funding_rate=funding_rate,
        next_funding_time=next_funding_ts,
        funding_interval_seconds=funding_interval_seconds,
        observed_at=observed_at or utc_now(),
    )


# ---------------------------------------------------------------------------
# exchangeInfo instrument normalizers
# ---------------------------------------------------------------------------


def _find_filter(filters: list[dict], filter_type: str) -> dict | None:
    """Return the first filter dict matching *filter_type*, or None."""
    for f in filters:
        if isinstance(f, dict) and f.get("filterType") == filter_type:
            return f
    return None


def _require_filter(data: dict, filter_type: str) -> dict:
    """Return the filter dict for *filter_type* or raise ValueError."""
    filters = data.get("filters")
    if not isinstance(filters, list):
        raise ValueError(
            f"Expected 'filters' to be a list, got {type(filters).__name__}"
        )
    result = _find_filter(filters, filter_type)
    if result is None:
        raise ValueError(f"Missing required filter: {filter_type!r}")
    return result


def normalize_spot_exchange_info_symbol(data: dict) -> InstrumentInfo:
    """Parse a single Binance spot exchangeInfo symbol entry.

    Required top-level fields: ``symbol``, ``baseAsset``, ``quoteAsset``,
    ``filters``.

    Required filters:
      - ``PRICE_FILTER`` with ``tickSize``
      - ``LOT_SIZE`` with ``stepSize``

    Optional:
      - ``LOT_SIZE.minQty``
      - ``NOTIONAL.minNotional`` or legacy ``MIN_NOTIONAL.minNotional``

    Representative payload (one element of ``exchangeInfo["symbols"]``)::

        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
                {"filterType": "NOTIONAL", "minNotional": "10.00000000"}
            ]
        }
    """
    symbol = _require_str(data, "symbol")
    base_asset = _require_str(data, "baseAsset")
    quote_asset = _require_str(data, "quoteAsset")

    price_filter = _require_filter(data, "PRICE_FILTER")
    tick_size = _require_decimal(price_filter, "tickSize")

    lot_size = _require_filter(data, "LOT_SIZE")
    step_size = _require_decimal(lot_size, "stepSize")
    min_qty = _optional_decimal(lot_size, "minQty")

    filters = data.get("filters", [])
    notional = _find_filter(filters, "NOTIONAL") or _find_filter(filters, "MIN_NOTIONAL")
    min_notional = None
    if notional is not None:
        min_notional = _optional_decimal(notional, "minNotional")

    return InstrumentInfo(
        exchange=_EXCHANGE,
        symbol=symbol,
        market_type=MarketType.SPOT,
        base_asset=base_asset,
        quote_asset=quote_asset,
        price_tick_size=tick_size,
        quantity_step_size=step_size,
        min_quantity=min_qty,
        min_notional=min_notional,
    )


def normalize_usdm_exchange_info_symbol(data: dict) -> InstrumentInfo:
    """Parse a single Binance USD-M futures exchangeInfo symbol entry.

    Required top-level fields: ``symbol``, ``baseAsset``, ``quoteAsset``,
    ``filters``.

    Required filters:
      - ``PRICE_FILTER`` with ``tickSize``
      - ``LOT_SIZE`` with ``stepSize``

    Optional:
      - ``LOT_SIZE.minQty``
      - ``MIN_NOTIONAL.notional`` (or ``minNotional``)

    Representative payload (one element of ``exchangeInfo["symbols"]``)::

        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5.00"}
            ]
        }
    """
    symbol = _require_str(data, "symbol")
    base_asset = _require_str(data, "baseAsset")
    quote_asset = _require_str(data, "quoteAsset")

    price_filter = _require_filter(data, "PRICE_FILTER")
    tick_size = _require_decimal(price_filter, "tickSize")

    lot_size = _require_filter(data, "LOT_SIZE")
    step_size = _require_decimal(lot_size, "stepSize")
    min_qty = _optional_decimal(lot_size, "minQty")

    min_notional_filter = _find_filter(data.get("filters", []), "MIN_NOTIONAL")
    min_notional = None
    if min_notional_filter is not None:
        min_notional = _optional_decimal(min_notional_filter, "notional")
        if min_notional is None:
            min_notional = _optional_decimal(min_notional_filter, "minNotional")

    return InstrumentInfo(
        exchange=_EXCHANGE,
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        base_asset=base_asset,
        quote_asset=quote_asset,
        price_tick_size=tick_size,
        quantity_step_size=step_size,
        min_quantity=min_qty,
        min_notional=min_notional,
    )
