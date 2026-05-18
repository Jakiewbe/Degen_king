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
