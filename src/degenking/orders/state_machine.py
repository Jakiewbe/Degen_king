"""Deterministic OrderIntent state machine."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from degenking.orders.intents import (
    TERMINAL_INTENT_STATES,
    OrderIntent,
    OrderIntentState,
)


class IllegalOrderStateTransitionError(ValueError):
    """Raised when an OrderIntent transition is not permitted."""


ALLOWED_TRANSITIONS: dict[OrderIntentState, frozenset[OrderIntentState]] = {
    OrderIntentState.INTENT_CREATED: frozenset(
        {
            OrderIntentState.RISK_APPROVED,
            OrderIntentState.RISK_REJECTED,
            OrderIntentState.DUPLICATE_SUPPRESSED,
        }
    ),
    OrderIntentState.RISK_APPROVED: frozenset(
        {
            OrderIntentState.SUBMITTED_TO_PAPER_BROKER,
            OrderIntentState.DUPLICATE_SUPPRESSED,
            OrderIntentState.STALE_CANCEL_REQUESTED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.SUBMITTED_TO_PAPER_BROKER: frozenset(
        {
            OrderIntentState.ACKNOWLEDGED,
            OrderIntentState.TIMEOUT,
            OrderIntentState.CANCELLED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.ACKNOWLEDGED: frozenset(
        {
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.FILLED,
            OrderIntentState.STALE_CANCEL_REQUESTED,
            OrderIntentState.TIMEOUT,
            OrderIntentState.CANCELLED,
            OrderIntentState.LEG_1_FILLED_LEG_2_FAILED,
        }
    ),
    OrderIntentState.PARTIALLY_FILLED: frozenset(
        {
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.FILLED,
            OrderIntentState.RESIDUAL_EXPOSURE,
            OrderIntentState.STALE_CANCEL_REQUESTED,
            OrderIntentState.TIMEOUT,
            OrderIntentState.CLEANUP_REQUIRED,
        }
    ),
    OrderIntentState.FILLED: frozenset(
        {
            OrderIntentState.RECONCILED,
            OrderIntentState.LEG_1_FILLED_LEG_2_FAILED,
            OrderIntentState.RESIDUAL_EXPOSURE,
        }
    ),
    OrderIntentState.RECONCILED: frozenset({OrderIntentState.POSITION_UPDATED}),
    OrderIntentState.POSITION_UPDATED: frozenset({OrderIntentState.CLOSED}),
    OrderIntentState.STALE_CANCEL_REQUESTED: frozenset(
        {
            OrderIntentState.CANCELLED,
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.RESIDUAL_EXPOSURE,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.TIMEOUT: frozenset(
        {
            OrderIntentState.STALE_CANCEL_REQUESTED,
            OrderIntentState.CLEANUP_REQUIRED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.LEG_1_FILLED_LEG_2_FAILED: frozenset(
        {
            OrderIntentState.RESIDUAL_EXPOSURE,
            OrderIntentState.CLEANUP_REQUIRED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.RESIDUAL_EXPOSURE: frozenset(
        {
            OrderIntentState.CLEANUP_REQUIRED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.CLEANUP_REQUIRED: frozenset(
        {
            OrderIntentState.CLEANUP_SUBMITTED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
    OrderIntentState.CLEANUP_SUBMITTED: frozenset(
        {
            OrderIntentState.RECONCILED,
            OrderIntentState.FAILED_MANUAL_RECOVERY_REQUIRED,
        }
    ),
}


def transition_intent(
    intent: OrderIntent,
    next_state: OrderIntentState,
    *,
    updated_at: datetime,
    filled_quantity: Decimal | None = None,
    exchange_order_id: str | None = None,
) -> OrderIntent:
    """Return a new intent after validating a state transition."""

    if next_state not in ALLOWED_TRANSITIONS.get(intent.state, frozenset()):
        raise IllegalOrderStateTransitionError(
            f"illegal order intent transition: {intent.state} -> {next_state}"
        )
    if intent.state in TERMINAL_INTENT_STATES:
        raise IllegalOrderStateTransitionError(
            f"terminal order intent cannot transition: {intent.state}"
        )

    next_filled_quantity = intent.filled_quantity
    if filled_quantity is not None:
        if filled_quantity < intent.filled_quantity:
            raise ValueError("filled_quantity cannot decrease")
        if filled_quantity > intent.quantity:
            raise ValueError("filled_quantity cannot exceed quantity")
        next_filled_quantity = filled_quantity

    if next_state == OrderIntentState.FILLED and next_filled_quantity != intent.quantity:
        raise ValueError("filled intent must have filled_quantity equal to quantity")
    if next_state == OrderIntentState.PARTIALLY_FILLED and not (
        Decimal("0") < next_filled_quantity < intent.quantity
    ):
        raise ValueError("partial fill requires 0 < filled_quantity < quantity")

    return replace(
        intent,
        state=next_state,
        updated_at=updated_at,
        filled_quantity=next_filled_quantity,
        exchange_order_id=exchange_order_id
        if exchange_order_id is not None
        else intent.exchange_order_id,
    )
