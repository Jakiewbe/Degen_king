"""Tests for pure exit-condition evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.positions.exits import (
    ExitDecision,
    ExitInputs,
    ExitReason,
    ExitThresholds,
    evaluate_exit_conditions,
)
from degenking.positions.manager import HedgedPosition, PositionState
from degenking.positions.pnl import PositionPnL

FROZEN_TIME = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_position(
    *,
    opened_at: datetime | None = None,
    delta_quantity: Decimal | None = None,
) -> HedgedPosition:
    return HedgedPosition(
        symbol="BTCUSDT",
        spot_quantity=Decimal("0.01"),
        perp_quantity=Decimal("-0.01"),
        spot_entry_notional_quote=Decimal("500"),
        perp_entry_notional_quote=Decimal("500"),
        fees_quote=Decimal("1.0"),
        slippage_quote=Decimal("0.5"),
        funding_pnl_quote=Decimal("2.0"),
        opened_at=opened_at or FROZEN_TIME,
        updated_at=FROZEN_TIME,
        state=PositionState.OPEN,
    )


def _make_pnl(
    *,
    total_pnl_quote: Decimal | None = None,
    delta_notional_quote: Decimal | None = None,
) -> PositionPnL:
    return PositionPnL(
        symbol="BTCUSDT",
        spot_market_value_quote=Decimal("501"),
        perp_mark_value_quote=Decimal("500"),
        spot_unrealized_pnl_quote=Decimal("1.0"),
        perp_unrealized_pnl_quote=Decimal("0"),
        funding_pnl_quote=Decimal("2.0"),
        fees_quote=Decimal("1.0"),
        slippage_quote=Decimal("0.5"),
        total_pnl_quote=total_pnl_quote if total_pnl_quote is not None else Decimal("1.5"),
        delta_quantity=Decimal("0"),
        delta_notional_quote=delta_notional_quote
        if delta_notional_quote is not None
        else Decimal("0"),
    )


def _make_thresholds() -> ExitThresholds:
    return ExitThresholds(
        min_exit_net_edge_bps=Decimal("1.0"),
        max_basis_deterioration_bps=Decimal("10.0"),
        max_delta_notional_quote=Decimal("50.0"),
        max_holding_seconds=3600,
        stop_loss_quote=Decimal("20.0"),
    )


def _make_inputs(
    *,
    position: HedgedPosition | None = None,
    pnl: PositionPnL | None = None,
    current_net_edge_bps: Decimal | None = None,
    entry_basis_bps: Decimal | None = None,
    current_basis_bps: Decimal | None = None,
    funding_rate_bps: Decimal | None = None,
    evaluated_at: datetime | None = None,
    thresholds: ExitThresholds | None = None,
    manual_shutdown: bool = False,
    kill_switch_active: bool = False,
) -> ExitInputs:
    return ExitInputs(
        position=position or _make_position(),
        pnl=pnl or _make_pnl(),
        current_net_edge_bps=current_net_edge_bps
        if current_net_edge_bps is not None
        else Decimal("5.0"),
        entry_basis_bps=entry_basis_bps
        if entry_basis_bps is not None
        else Decimal("2.0"),
        current_basis_bps=current_basis_bps
        if current_basis_bps is not None
        else Decimal("3.0"),
        funding_rate_bps=funding_rate_bps
        if funding_rate_bps is not None
        else Decimal("10.0"),
        evaluated_at=evaluated_at or FROZEN_TIME,
        thresholds=thresholds or _make_thresholds(),
        manual_shutdown=manual_shutdown,
        kill_switch_active=kill_switch_active,
    )


# ---------------------------------------------------------------------------
# No exit: everything healthy
# ---------------------------------------------------------------------------


def test_no_exit_when_all_healthy() -> None:
    result = evaluate_exit_conditions(_make_inputs())

    assert isinstance(result, ExitDecision)
    assert result.should_exit is False
    assert result.reasons == ()


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_forces_exit() -> None:
    result = evaluate_exit_conditions(_make_inputs(kill_switch_active=True))

    assert result.should_exit is True
    assert ExitReason.KILL_SWITCH in result.reasons


# ---------------------------------------------------------------------------
# Manual shutdown
# ---------------------------------------------------------------------------


def test_manual_shutdown_forces_exit() -> None:
    result = evaluate_exit_conditions(_make_inputs(manual_shutdown=True))

    assert result.should_exit is True
    assert ExitReason.MANUAL_SHUTDOWN in result.reasons


# ---------------------------------------------------------------------------
# Funding not favorable
# ---------------------------------------------------------------------------


def test_funding_not_favorable_zero_rate() -> None:
    result = evaluate_exit_conditions(_make_inputs(funding_rate_bps=Decimal("0")))

    assert result.should_exit is True
    assert ExitReason.FUNDING_NOT_FAVORABLE in result.reasons


def test_funding_not_favorable_negative_rate() -> None:
    result = evaluate_exit_conditions(_make_inputs(funding_rate_bps=Decimal("-5.0")))

    assert result.should_exit is True
    assert ExitReason.FUNDING_NOT_FAVORABLE in result.reasons


# ---------------------------------------------------------------------------
# Net edge below threshold
# ---------------------------------------------------------------------------


def test_net_edge_below_threshold() -> None:
    result = evaluate_exit_conditions(
        _make_inputs(current_net_edge_bps=Decimal("0.5"))
    )

    assert result.should_exit is True
    assert ExitReason.NET_EDGE_BELOW_EXIT_THRESHOLD in result.reasons


def test_net_edge_at_threshold_no_exit_for_this_reason() -> None:
    """Edge at exactly threshold is not below; it must be strictly below."""
    result = evaluate_exit_conditions(
        _make_inputs(current_net_edge_bps=Decimal("1.0"))
    )

    assert ExitReason.NET_EDGE_BELOW_EXIT_THRESHOLD not in result.reasons


# ---------------------------------------------------------------------------
# Basis deterioration
# ---------------------------------------------------------------------------


def test_basis_deterioration() -> None:
    result = evaluate_exit_conditions(
        _make_inputs(
            entry_basis_bps=Decimal("2.0"),
            current_basis_bps=Decimal("15.0"),
        )
    )

    assert result.should_exit is True
    assert ExitReason.BASIS_DETERIORATION in result.reasons


def test_basis_deterioration_negative_direction() -> None:
    result = evaluate_exit_conditions(
        _make_inputs(
            entry_basis_bps=Decimal("5.0"),
            current_basis_bps=Decimal("-8.0"),
        )
    )

    assert result.should_exit is True
    assert ExitReason.BASIS_DETERIORATION in result.reasons


def test_basis_deterioration_within_limit() -> None:
    result = evaluate_exit_conditions(
        _make_inputs(
            entry_basis_bps=Decimal("2.0"),
            current_basis_bps=Decimal("12.0"),
        )
    )

    assert ExitReason.BASIS_DETERIORATION not in result.reasons


# ---------------------------------------------------------------------------
# Delta too large
# ---------------------------------------------------------------------------


def test_delta_too_large() -> None:
    pnl = _make_pnl(delta_notional_quote=Decimal("100.0"))
    result = evaluate_exit_conditions(_make_inputs(pnl=pnl))

    assert result.should_exit is True
    assert ExitReason.DELTA_TOO_LARGE in result.reasons


def test_delta_within_limit() -> None:
    pnl = _make_pnl(delta_notional_quote=Decimal("50.0"))
    result = evaluate_exit_conditions(_make_inputs(pnl=pnl))

    assert ExitReason.DELTA_TOO_LARGE not in result.reasons


# ---------------------------------------------------------------------------
# Max holding time
# ---------------------------------------------------------------------------


def test_max_holding_time_reached() -> None:
    old_open = FROZEN_TIME - timedelta(seconds=3600)
    position = _make_position(opened_at=old_open)
    result = evaluate_exit_conditions(_make_inputs(position=position))

    assert result.should_exit is True
    assert ExitReason.MAX_HOLDING_TIME_REACHED in result.reasons


def test_max_holding_time_exceeded() -> None:
    old_open = FROZEN_TIME - timedelta(seconds=5000)
    position = _make_position(opened_at=old_open)
    result = evaluate_exit_conditions(_make_inputs(position=position))

    assert ExitReason.MAX_HOLDING_TIME_REACHED in result.reasons


def test_holding_time_within_limit() -> None:
    old_open = FROZEN_TIME - timedelta(seconds=1800)
    position = _make_position(opened_at=old_open)
    result = evaluate_exit_conditions(_make_inputs(position=position))

    assert ExitReason.MAX_HOLDING_TIME_REACHED not in result.reasons


# ---------------------------------------------------------------------------
# Stop loss
# ---------------------------------------------------------------------------


def test_stop_loss_triggered() -> None:
    pnl = _make_pnl(total_pnl_quote=Decimal("-25.0"))
    result = evaluate_exit_conditions(_make_inputs(pnl=pnl))

    assert result.should_exit is True
    assert ExitReason.STOP_LOSS in result.reasons


def test_stop_loss_at_limit() -> None:
    pnl = _make_pnl(total_pnl_quote=Decimal("-20.0"))
    result = evaluate_exit_conditions(_make_inputs(pnl=pnl))

    assert ExitReason.STOP_LOSS in result.reasons


def test_stop_loss_not_triggered() -> None:
    pnl = _make_pnl(total_pnl_quote=Decimal("-5.0"))
    result = evaluate_exit_conditions(_make_inputs(pnl=pnl))

    assert ExitReason.STOP_LOSS not in result.reasons


# ---------------------------------------------------------------------------
# Multiple reasons
# ---------------------------------------------------------------------------


def test_multiple_reasons_accumulate() -> None:
    old_open = FROZEN_TIME - timedelta(seconds=4000)
    position = _make_position(opened_at=old_open)
    pnl = _make_pnl(
        total_pnl_quote=Decimal("-25.0"),
        delta_notional_quote=Decimal("100.0"),
    )
    result = evaluate_exit_conditions(
        _make_inputs(
            position=position,
            pnl=pnl,
            funding_rate_bps=Decimal("-5.0"),
            current_net_edge_bps=Decimal("0.1"),
            entry_basis_bps=Decimal("2.0"),
            current_basis_bps=Decimal("20.0"),
            kill_switch_active=True,
        )
    )

    assert result.should_exit is True
    assert len(result.reasons) >= 6
    assert ExitReason.KILL_SWITCH in result.reasons
    assert ExitReason.FUNDING_NOT_FAVORABLE in result.reasons
    assert ExitReason.NET_EDGE_BELOW_EXIT_THRESHOLD in result.reasons
    assert ExitReason.BASIS_DETERIORATION in result.reasons
    assert ExitReason.DELTA_TOO_LARGE in result.reasons
    assert ExitReason.MAX_HOLDING_TIME_REACHED in result.reasons
    assert ExitReason.STOP_LOSS in result.reasons


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_exit_decision_is_frozen() -> None:
    decision = ExitDecision(should_exit=True, reasons=(ExitReason.STOP_LOSS,))
    # Frozen dataclass: attempting to set an attribute should raise.
    raised = False
    try:
        decision.should_exit = False  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised
