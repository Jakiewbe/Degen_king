"""Layer B in-flight execution guards.

Pure functions that evaluate whether a paper OrderIntent (or its aftermath)
requires blocking new entries or entering manual recovery.

No broker calls. No order creation. No exchange access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class ExecutionGuardReason(StrEnum):
    """Reasons an execution guard has fired."""

    ORDER_TIMEOUT = "order_timeout"
    STALE_ORDER = "stale_order"
    DUPLICATE_INTENT = "duplicate_intent"
    PARTIAL_FILL_TIMEOUT = "partial_fill_timeout"
    SINGLE_LEG_FAILURE = "single_leg_failure"
    RESIDUAL_EXPOSURE = "residual_exposure"
    SLIPPAGE_BREACH = "slippage_breach"
    UNRECONCILED_STATE = "unreconciled_state"


@dataclass(frozen=True, slots=True)
class ExecutionGuardInputs:
    """All inputs needed for Layer B guard evaluation."""

    intent_state: str
    created_at: datetime
    evaluated_at: datetime
    order_timeout_seconds: int
    stale_order_seconds: int
    max_unhedged_seconds: int
    slippage_bps: Decimal
    max_slippage_bps: Decimal
    has_duplicate_intent: bool = False
    leg_1_filled_leg_2_failed: bool = False
    residual_exposure: bool = False
    reconciled: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionGuardDecision:
    """Result of Layer B execution guard evaluation."""

    passed: bool
    reasons: tuple[ExecutionGuardReason, ...]
    block_new_entries: bool
    manual_recovery_required: bool


# Per-reason configuration: (block_new_entries, manual_recovery_required)
_REASON_EFFECT: dict[ExecutionGuardReason, tuple[bool, bool]] = {
    ExecutionGuardReason.ORDER_TIMEOUT: (True, False),
    ExecutionGuardReason.STALE_ORDER: (True, False),
    ExecutionGuardReason.DUPLICATE_INTENT: (True, False),
    ExecutionGuardReason.PARTIAL_FILL_TIMEOUT: (False, True),
    ExecutionGuardReason.SINGLE_LEG_FAILURE: (True, True),
    ExecutionGuardReason.RESIDUAL_EXPOSURE: (True, True),
    ExecutionGuardReason.SLIPPAGE_BREACH: (True, False),
    ExecutionGuardReason.UNRECONCILED_STATE: (True, True),
}

_ACTIVE_ORDER_STATES = frozenset(
    {
        "risk_approved",
        "submitted_to_paper_broker",
        "acknowledged",
        "partially_filled",
        "stale_cancel_requested",
        "cleanup_submitted",
    }
)
_PARTIAL_FILL_STATES = frozenset({"partially_filled"})


def evaluate_execution_guards(inputs: ExecutionGuardInputs) -> ExecutionGuardDecision:
    """Evaluate all Layer B in-flight execution guards.

    Returns an ExecutionGuardDecision with accumulated reasons.
    Block and manual-recovery flags are the union of each triggered reason's effect.
    """
    reasons: list[ExecutionGuardReason] = []

    _validate_inputs(inputs)
    age_seconds = (inputs.evaluated_at - inputs.created_at).total_seconds()
    intent_state = inputs.intent_state.lower()

    # --- Time-based guards ---
    if intent_state in _ACTIVE_ORDER_STATES and age_seconds > inputs.order_timeout_seconds:
        reasons.append(ExecutionGuardReason.ORDER_TIMEOUT)
    if intent_state in _ACTIVE_ORDER_STATES and age_seconds > inputs.stale_order_seconds:
        reasons.append(ExecutionGuardReason.STALE_ORDER)
    if intent_state in _PARTIAL_FILL_STATES and age_seconds > inputs.max_unhedged_seconds:
        reasons.append(ExecutionGuardReason.PARTIAL_FILL_TIMEOUT)

    # --- Structural guards ---
    if inputs.has_duplicate_intent:
        reasons.append(ExecutionGuardReason.DUPLICATE_INTENT)
    if inputs.leg_1_filled_leg_2_failed:
        reasons.append(ExecutionGuardReason.SINGLE_LEG_FAILURE)
    if inputs.residual_exposure:
        reasons.append(ExecutionGuardReason.RESIDUAL_EXPOSURE)

    # --- Price / quality guards ---
    if inputs.slippage_bps > inputs.max_slippage_bps:
        reasons.append(ExecutionGuardReason.SLIPPAGE_BREACH)

    # --- State integrity guard ---
    if not inputs.reconciled:
        reasons.append(ExecutionGuardReason.UNRECONCILED_STATE)

    block = False
    manual_recovery = False
    for reason in reasons:
        effect_block, effect_manual = _REASON_EFFECT[reason]
        if effect_block:
            block = True
        if effect_manual:
            manual_recovery = True

    return ExecutionGuardDecision(
        passed=len(reasons) == 0,
        reasons=tuple(reasons),
        block_new_entries=block,
        manual_recovery_required=manual_recovery,
    )


def _validate_inputs(inputs: ExecutionGuardInputs) -> None:
    if inputs.evaluated_at < inputs.created_at:
        raise ValueError("evaluated_at cannot be before created_at")
    if inputs.order_timeout_seconds < 0:
        raise ValueError("order_timeout_seconds must be non-negative")
    if inputs.stale_order_seconds < 0:
        raise ValueError("stale_order_seconds must be non-negative")
    if inputs.max_unhedged_seconds < 0:
        raise ValueError("max_unhedged_seconds must be non-negative")
    if inputs.slippage_bps < 0:
        raise ValueError("slippage_bps must be non-negative")
    if inputs.max_slippage_bps < 0:
        raise ValueError("max_slippage_bps must be non-negative")
