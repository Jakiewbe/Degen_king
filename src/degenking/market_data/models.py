"""Normalized read-only market data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from degenking.common.enums import MarketType


@dataclass(frozen=True, slots=True)
class TickerSnapshot:
    exchange: str
    symbol: str
    market_type: MarketType
    bid: Decimal
    ask: Decimal
    observed_at: datetime
    mark: Decimal | None = None
    index: Decimal | None = None

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def mark_or_mid(self) -> Decimal:
        return self.mark if self.mark is not None else self.mid


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    exchange: str
    symbol: str
    market_type: MarketType
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    observed_at: datetime
    checksum: str | None = None

    def top_depth_quote(self, levels: int = 10) -> Decimal:
        """Return approximate quote depth across top bid and ask levels."""

        bid_depth = sum(
            (level.price * level.quantity for level in self.bids[:levels]),
            Decimal("0"),
        )
        ask_depth = sum(
            (level.price * level.quantity for level in self.asks[:levels]),
            Decimal("0"),
        )
        return bid_depth + ask_depth


@dataclass(frozen=True, slots=True)
class FundingRateSnapshot:
    exchange: str
    symbol: str
    funding_rate: Decimal
    next_funding_time: datetime
    funding_interval_seconds: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class LatencySample:
    exchange: str
    channel: str
    latency_ms: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ExchangeStatus:
    exchange: str
    environment: str
    status: str
    maintenance: bool
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    """Static instrument metadata parsed from exchangeInfo."""

    exchange: str
    symbol: str
    market_type: MarketType
    base_asset: str
    quote_asset: str
    price_tick_size: Decimal
    quantity_step_size: Decimal
    min_quantity: Decimal | None = None
    min_notional: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PrecisionCheckResult:
    """Result of rounding and validating an order size against instrument filters."""

    rounded_price: Decimal
    rounded_quantity: Decimal
    notional_quote: Decimal
    min_quantity_ok: bool
    min_notional_ok: bool
    passed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    asset: str
    wallet_balance: Decimal
    available_balance: Decimal
    locked_balance: Decimal


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    exchange: str
    equity: Decimal
    available_margin: Decimal
    account_mode: str
    balances: tuple[BalanceSnapshot, ...]
    observed_at: datetime
