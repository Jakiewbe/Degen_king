"""Tests for pure execution guard evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.risk.execution_guards import (
    ExecutionGuardDecision,
    ExecutionGuardInputs,
    ExecutionGuardReason,
    evaluate_execution_guards,
)

FROZEN_TIME = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)


def _make_inputs(
    *,
    intent_state: str = "acknowledged",
    created_at: datetime | None = None,
    evaluated_at: datetime | None = None,
    order_timeout_seconds: int = 30,
    stale_order_seconds: int = 60,
    max_unhedged_seconds: int = 120,
    slippage_bps: Decimal | None = None,
    max_slippage_bps: Decimal | None = None,
    has_duplicate_intent: bool = False,
    leg_1_filled_leg_2_failed: bool = False,
    residual_exposure: bool = False,
    reconciled: bool = True,
) -> ExecutionGuardInputs:
    return ExecutionGuardInputs(
        intent_state=intent_state,
        created_at=created_at or FROZEN_TIME,
        evaluated_at=evaluated_at or FROZEN_TIME,
        order_timeout_seconds=order_timeout_seconds,
        stale_order_seconds=stale_order_seconds,
        max_unhedged_seconds=max_unhedged_seconds,
        slippage_bps=slippage_bps if slippage_bps is not None else Decimal("3.0"),
        max_slippage_bps=max_slippage_bps if max_slippage_bps is not None else Decimal("10.0"),
        has_duplicate_intent=has_duplicate_intent,
        leg_1_filled_leg_2_failed=leg_1_filled_leg_2_failed,
        residual_exposure=residual_exposure,
        reconciled=reconciled,
    )


# ---------------------------------------------------------------------------
# Clean pass
# ---------------------------------------------------------------------------


def test_clean_state_passes_all_guards() -> None:
    result = evaluate_execution_guards(_make_inputs())

    assert isinstance(result, ExecutionGuardDecision)
    assert result.passed is True
    assert result.reasons == ()
    assert result.block_new_entries is False
    assert result.manual_recovery_required is False


# ---------------------------------------------------------------------------
# Order timeout
# ---------------------------------------------------------------------------


def test_order_timeout_blocks_new_entries() -> None:
    created = FROZEN_TIME - timedelta(seconds=31)
    result = evaluate_execution_guards(_make_inputs(created_at=created))

    assert result.passed is False
    assert ExecutionGuardReason.ORDER_TIMEOUT in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is False


def test_order_within_timeout_passes() -> None:
    created = FROZEN_TIME - timedelta(seconds=30)
    result = evaluate_execution_guards(_make_inputs(created_at=created))

    assert ExecutionGuardReason.ORDER_TIMEOUT not in result.reasons


def test_filled_old_intent_does_not_trigger_order_timeout() -> None:
    created = FROZEN_TIME - timedelta(seconds=300)
    result = evaluate_execution_guards(
        _make_inputs(intent_state="filled", created_at=created)
    )

    assert ExecutionGuardReason.ORDER_TIMEOUT not in result.reasons
    assert ExecutionGuardReason.STALE_ORDER not in result.reasons


# ---------------------------------------------------------------------------
# Stale order
# ---------------------------------------------------------------------------


def test_stale_order_blocks_new_entries() -> None:
    created = FROZEN_TIME - timedelta(seconds=61)
    result = evaluate_execution_guards(_make_inputs(created_at=created))

    assert result.passed is False
    assert ExecutionGuardReason.STALE_ORDER in result.reasons
    assert result.block_new_entries is True


def test_stale_order_within_limit_passes() -> None:
    created = FROZEN_TIME - timedelta(seconds=60)
    result = evaluate_execution_guards(_make_inputs(created_at=created))

    assert ExecutionGuardReason.STALE_ORDER not in result.reasons


# ---------------------------------------------------------------------------
# Duplicate intent
# ---------------------------------------------------------------------------


def test_duplicate_intent_blocks_new_entries() -> None:
    result = evaluate_execution_guards(_make_inputs(has_duplicate_intent=True))

    assert result.passed is False
    assert ExecutionGuardReason.DUPLICATE_INTENT in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is False


# ---------------------------------------------------------------------------
# Partial fill timeout
# ---------------------------------------------------------------------------


def test_partial_fill_timeout_manual_recovery() -> None:
    created = FROZEN_TIME - timedelta(seconds=121)
    result = evaluate_execution_guards(
        _make_inputs(intent_state="partially_filled", created_at=created)
    )

    assert result.passed is False
    assert ExecutionGuardReason.PARTIAL_FILL_TIMEOUT in result.reasons
    assert result.manual_recovery_required is True


def test_partial_fill_within_time_passes() -> None:
    created = FROZEN_TIME - timedelta(seconds=120)
    result = evaluate_execution_guards(
        _make_inputs(intent_state="partially_filled", created_at=created)
    )

    assert ExecutionGuardReason.PARTIAL_FILL_TIMEOUT not in result.reasons


def test_acknowledged_old_intent_does_not_trigger_partial_fill_timeout() -> None:
    created = FROZEN_TIME - timedelta(seconds=300)
    result = evaluate_execution_guards(_make_inputs(created_at=created))

    assert ExecutionGuardReason.ORDER_TIMEOUT in result.reasons
    assert ExecutionGuardReason.STALE_ORDER in result.reasons
    assert ExecutionGuardReason.PARTIAL_FILL_TIMEOUT not in result.reasons


# ---------------------------------------------------------------------------
# Single-leg failure
# ---------------------------------------------------------------------------


def test_single_leg_failure_blocks_and_manual_recovery() -> None:
    result = evaluate_execution_guards(_make_inputs(leg_1_filled_leg_2_failed=True))

    assert result.passed is False
    assert ExecutionGuardReason.SINGLE_LEG_FAILURE in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is True


# ---------------------------------------------------------------------------
# Residual exposure
# ---------------------------------------------------------------------------


def test_residual_exposure_blocks_and_manual_recovery() -> None:
    result = evaluate_execution_guards(_make_inputs(residual_exposure=True))

    assert result.passed is False
    assert ExecutionGuardReason.RESIDUAL_EXPOSURE in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is True


# ---------------------------------------------------------------------------
# Slippage breach
# ---------------------------------------------------------------------------


def test_slippage_breach_blocks_new_entries() -> None:
    result = evaluate_execution_guards(
        _make_inputs(slippage_bps=Decimal("15.0"), max_slippage_bps=Decimal("10.0"))
    )

    assert result.passed is False
    assert ExecutionGuardReason.SLIPPAGE_BREACH in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is False


def test_slippage_within_limit_passes() -> None:
    result = evaluate_execution_guards(
        _make_inputs(slippage_bps=Decimal("10.0"), max_slippage_bps=Decimal("10.0"))
    )

    assert ExecutionGuardReason.SLIPPAGE_BREACH not in result.reasons


# ---------------------------------------------------------------------------
# Unreconciled state
# ---------------------------------------------------------------------------


def test_unreconciled_state_blocks_and_manual_recovery() -> None:
    result = evaluate_execution_guards(_make_inputs(reconciled=False))

    assert result.passed is False
    assert ExecutionGuardReason.UNRECONCILED_STATE in result.reasons
    assert result.block_new_entries is True
    assert result.manual_recovery_required is True


# ---------------------------------------------------------------------------
# Multiple reasons
# ---------------------------------------------------------------------------


def test_multiple_reasons_accumulate() -> None:
    created = FROZEN_TIME - timedelta(seconds=150)
    result = evaluate_execution_guards(
        _make_inputs(
            created_at=created,
            intent_state="partially_filled",
            slippage_bps=Decimal("20.0"),
            has_duplicate_intent=True,
            leg_1_filled_leg_2_failed=True,
            residual_exposure=True,
            reconciled=False,
        )
    )

    assert result.passed is False
    assert result.block_new_entries is True
    assert result.manual_recovery_required is True
    assert len(result.reasons) >= 7
    assert ExecutionGuardReason.ORDER_TIMEOUT in result.reasons
    assert ExecutionGuardReason.STALE_ORDER in result.reasons
    assert ExecutionGuardReason.DUPLICATE_INTENT in result.reasons
    assert ExecutionGuardReason.PARTIAL_FILL_TIMEOUT in result.reasons
    assert ExecutionGuardReason.SINGLE_LEG_FAILURE in result.reasons
    assert ExecutionGuardReason.RESIDUAL_EXPOSURE in result.reasons
    assert ExecutionGuardReason.SLIPPAGE_BREACH in result.reasons
    assert ExecutionGuardReason.UNRECONCILED_STATE in result.reasons


def test_rejects_negative_slippage() -> None:
    try:
        evaluate_execution_guards(_make_inputs(slippage_bps=Decimal("-1")))
    except ValueError as exc:
        assert "slippage_bps" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# Decision immutability
# ---------------------------------------------------------------------------


def test_execution_guard_decision_is_frozen() -> None:
    decision = ExecutionGuardDecision(
        passed=False,
        reasons=(ExecutionGuardReason.ORDER_TIMEOUT,),
        block_new_entries=True,
        manual_recovery_required=False,
    )
    raised = False
    try:
        decision.passed = True  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised
