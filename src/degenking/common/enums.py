"""Shared enums used across deterministic subsystems."""

from __future__ import annotations

from enum import StrEnum


class RuntimeMode(StrEnum):
    """Supported MVP runtime modes."""

    MONITOR = "monitor"
    PAPER = "paper"


class ExchangeName(StrEnum):
    """MVP exchange target."""

    BYBIT = "bybit"


class ExchangeEnvironment(StrEnum):
    """Supported non-live exchange environments."""

    DEMO = "demo"
    TESTNET = "testnet"


class KillSwitchMode(StrEnum):
    """Kill-switch behavior by runtime environment."""

    SIMULATED = "simulated"


class MarketType(StrEnum):
    """Market type for normalized data."""

    SPOT = "spot"
    PERPETUAL = "perpetual"


class FreshnessStatus(StrEnum):
    """Freshness result for time-sensitive market data."""

    FRESH = "fresh"
    STALE = "stale"


class EventSeverity(StrEnum):
    """Audit/system event severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
