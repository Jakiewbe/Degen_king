"""Pure dataclass table-model contracts for future DB/ORM mapping.

No SQLAlchemy. No database connection. No ORM. No broker calls.
Frozen dataclasses describing the shape of each persistence row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaseRecord:
    """Fields common to every primary event and decision table.

    Subclasses declare ``slots=True``; the base omits it so that
    ``__slots__`` only contains the subclass-specific fields.
    """

    id: str
    trace_id: str | None = None
    run_id: str | None = None
    strategy_id: str | None = None
    config_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigVersionRecord(BaseRecord):
    """Immutable config snapshot."""

    mode: str | None = None
    exchange: str | None = None
    symbols: tuple[str, ...] = ()
    raw_config: str | None = None
    validation_status: str | None = None
    validation_result: str | None = None


# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExchangeStatusRecord(BaseRecord):
    """Exchange health and maintenance state."""

    exchange: str | None = None
    environment: str | None = None
    status: str | None = None
    maintenance: bool = False
    last_heartbeat_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LatencySampleRecord(BaseRecord):
    """REST / WebSocket latency measurement."""

    exchange: str | None = None
    channel: str | None = None
    latency_ms: int = 0
    measured_at: datetime | None = None


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarketTickRecord(BaseRecord):
    """Normalized spot or perp ticker snapshot."""

    symbol: str | None = None
    market_type: str | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    mid: Decimal | None = None
    mark: Decimal | None = None
    index: Decimal | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OrderBookSnapshotRecord(BaseRecord):
    """Depth snapshot for one side of the book."""

    symbol: str | None = None
    market_type: str | None = None
    bids: str | None = None
    asks: str | None = None
    depth_usd: Decimal | None = None
    checksum: int | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FundingRateRecord(BaseRecord):
    """Funding rate observation."""

    symbol: str | None = None
    funding_rate: Decimal | None = None
    next_funding_time: datetime | None = None
    funding_interval_seconds: int | None = None
    observed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountSnapshotRecord(BaseRecord):
    """Account-level read-only state."""

    exchange: str | None = None
    equity: Decimal | None = None
    available_margin: Decimal | None = None
    account_mode: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BalanceSnapshotRecord(BaseRecord):
    """Per-asset balance line."""

    asset: str | None = None
    wallet_balance: Decimal | None = None
    available_balance: Decimal | None = None
    locked_balance: Decimal | None = None
    account_snapshot_id: str | None = None


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignalRecord(BaseRecord):
    """Strategy candidate evaluation."""

    symbol: str | None = None
    net_edge_quote: Decimal | None = None
    net_edge_bps: Decimal | None = None
    suggested_notional: Decimal | None = None
    status: str | None = None
    reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskCheckRecord(BaseRecord):
    """One row per pre-trade / in-flight risk check."""

    decision_id: str | None = None
    check_name: str | None = None
    passed: bool = False
    observed_value: str | None = None
    limit_value: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RiskIncidentRecord(BaseRecord):
    """Risk event requiring operator attention or recovery."""

    incident_type: str | None = None
    severity: str | None = None
    trigger: str | None = None
    action_taken: str | None = None
    manual_reset_required: bool = False


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderIntentRecord(BaseRecord):
    """Internal desired action before any exchange order."""

    idempotency_key: str | None = None
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    leg: str | None = None
    side: str | None = None
    symbol: str | None = None
    quantity: Decimal | None = None
    limit_price: Decimal | None = None
    state: str | None = None
    filled_quantity: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OrderRecord(BaseRecord):
    """Paper or future exchange order."""

    client_order_id: str | None = None
    exchange_order_id: str | None = None
    intent_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    quantity: Decimal | None = None
    limit_price: Decimal | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class FillRecord(BaseRecord):
    """One fill event."""

    order_id: str | None = None
    intent_id: str | None = None
    symbol: str | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None
    fee: Decimal | None = None
    liquidity: str | None = None
    filled_at: datetime | None = None


# ---------------------------------------------------------------------------
# Positions / PnL
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PositionRecord(BaseRecord):
    """Hedged paper position state."""

    symbol: str | None = None
    spot_quantity: Decimal | None = None
    perp_quantity: Decimal | None = None
    delta_quantity: Decimal | None = None
    spot_entry_notional: Decimal | None = None
    perp_entry_notional: Decimal | None = None
    entry_basis_bps: Decimal | None = None
    fees_quote: Decimal | None = None
    slippage_quote: Decimal | None = None
    funding_pnl_quote: Decimal | None = None
    state: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PnlRecord(BaseRecord):
    """PnL attribution snapshot."""

    symbol: str | None = None
    position_id: str | None = None
    funding_pnl: Decimal | None = None
    trading_fees: Decimal | None = None
    slippage_cost: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    total_pnl: Decimal | None = None
    calculated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReconciliationRunRecord(BaseRecord):
    """Expected-vs-observed paper-state comparison."""

    symbol: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expected_state: str | None = None
    observed_state: str | None = None
    status: str | None = None
    discrepancy_count: int = 0
    discrepancies: str | None = None
    manual_recovery_required: bool = False


# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManualActionRecord(BaseRecord):
    """Operator intervention or recovery action."""

    actor: str | None = None
    action: str | None = None
    reason: str | None = None
    affected_trace_id: str | None = None
    affected_position_id: str | None = None
    performed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AgentReportRecord(BaseRecord):
    """Read-only agent output."""

    report_type: str | None = None
    source_views: tuple[str, ...] = ()
    content: str | None = None
    generated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SystemEventRecord(BaseRecord):
    """General system event."""

    component: str | None = None
    severity: str | None = None
    event_type: str | None = None
    message: str | None = None
    payload: str | None = None


@dataclass(frozen=True, slots=True)
class RawExchangeEventRecord(BaseRecord):
    """Raw inbound exchange payload for replay / debug."""

    source: str | None = None
    channel: str | None = None
    payload: str | None = None
    received_at: datetime | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def require_non_empty(value: str | None, field: str) -> str:
    """Raise ValueError if *value* is None or empty."""
    if not value:
        raise ValueError(f"{field} must be non-empty")
    return value


def record_identity(record: BaseRecord) -> tuple[str, str | None, str | None]:
    """Return (record_type, id, trace_id) for a BaseRecord."""
    return (type(record).__name__, record.id, record.trace_id)
