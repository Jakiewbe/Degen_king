"""Order intent data model.

Order intents describe desired internal actions. They are not exchange orders,
and this module has no broker or exchange dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class OrderIntentLeg(StrEnum):
    """Supported hedged-arbitrage intent legs."""

    SPOT_OPEN = "spot_open"
    PERP_OPEN = "perp_open"
    SPOT_CLOSE = "spot_close"
    PERP_CLOSE = "perp_close"
    CLEANUP = "cleanup"


class OrderSide(StrEnum):
    """Normalized order side."""

    BUY = "buy"
    SELL = "sell"


class OrderIntentState(StrEnum):
    """OrderIntent lifecycle states."""

    INTENT_CREATED = "intent_created"
    RISK_APPROVED = "risk_approved"
    SUBMITTED_TO_PAPER_BROKER = "submitted_to_paper_broker"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    RECONCILED = "reconciled"
    POSITION_UPDATED = "position_updated"
    CLOSED = "closed"
    RISK_REJECTED = "risk_rejected"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    STALE_CANCEL_REQUESTED = "stale_cancel_requested"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    LEG_1_FILLED_LEG_2_FAILED = "leg_1_filled_leg_2_failed"
    RESIDUAL_EXPOSURE = "residual_exposure"
    CLEANUP_REQUIRED = "cleanup_required"
    CLEANUP_SUBMITTED = "cleanup_submitted"
    FAILED_MANUAL_RECOVERY_REQUIRED = "failed_manual_recovery_required"


TERMINAL_INTENT_STATES = frozenset(
    {
        OrderIntentState.CLOSED,
        OrderIntentState.RISK_REJECTED,
        OrderIntentState.DUPLICATE_SUPPRESSED,
        OrderIntentState.CANCELLED,
        OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
    }
)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """Desired action before paper-broker or future exchange submission."""

    intent_id: str
    trace_id: str
    run_id: str
    strategy_id: str
    config_hash: str
    idempotency_key: str
    symbol: str
    leg: OrderIntentLeg
    side: OrderSide
    quantity: Decimal
    notional_quote: Decimal
    limit_price: Decimal
    client_order_id: str
    created_at: datetime
    updated_at: datetime
    state: OrderIntentState = OrderIntentState.INTENT_CREATED
    exchange_order_id: str | None = None
    filled_quantity: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _require_non_empty(self.intent_id, "intent_id")
        _require_non_empty(self.trace_id, "trace_id")
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.strategy_id, "strategy_id")
        _require_non_empty(self.config_hash, "config_hash")
        _require_non_empty(self.idempotency_key, "idempotency_key")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.client_order_id, "client_order_id")
        _require_positive(self.quantity, "quantity")
        _require_positive(self.notional_quote, "notional_quote")
        _require_positive(self.limit_price, "limit_price")
        if self.filled_quantity < 0:
            raise ValueError("filled_quantity must be non-negative")
        if self.filled_quantity > self.quantity:
            raise ValueError("filled_quantity cannot exceed quantity")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    @property
    def residual_quantity(self) -> Decimal:
        """Unfilled quantity remaining on this intent."""

        return self.quantity - self.filled_quantity

    @property
    def is_terminal(self) -> bool:
        """Whether no further normal state transition is expected."""

        return self.state in TERMINAL_INTENT_STATES


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} is required")


def _require_positive(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
