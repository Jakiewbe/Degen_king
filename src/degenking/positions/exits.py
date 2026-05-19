"""Pure exit-condition evaluation for paper positions.

No order creation. No broker calls. No exchange access. Deterministic only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from degenking.positions.manager import HedgedPosition
from degenking.positions.pnl import PositionPnL


class ExitReason(StrEnum):
    """Reasons a paper position should be exited."""

    FUNDING_NOT_FAVORABLE = "funding_not_favorable"
    NET_EDGE_BELOW_EXIT_THRESHOLD = "net_edge_below_exit_threshold"
    BASIS_DETERIORATION = "basis_deterioration"
    DELTA_TOO_LARGE = "delta_too_large"
    MAX_HOLDING_TIME_REACHED = "max_holding_time_reached"
    STOP_LOSS = "stop_loss"
    MANUAL_SHUTDOWN = "manual_shutdown"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True, slots=True)
class ExitThresholds:
    """Configurable thresholds for exit evaluation."""

    min_exit_net_edge_bps: Decimal
    max_basis_deterioration_bps: Decimal
    max_delta_notional_quote: Decimal
    max_holding_seconds: int
    stop_loss_quote: Decimal


@dataclass(frozen=True, slots=True)
class ExitInputs:
    """All inputs needed to evaluate exit conditions for one position."""

    position: HedgedPosition
    pnl: PositionPnL
    current_net_edge_bps: Decimal
    entry_basis_bps: Decimal
    current_basis_bps: Decimal
    funding_rate_bps: Decimal
    evaluated_at: datetime
    thresholds: ExitThresholds
    manual_shutdown: bool = False
    kill_switch_active: bool = False


@dataclass(frozen=True, slots=True)
class ExitDecision:
    """Result of exit-condition evaluation."""

    should_exit: bool
    reasons: tuple[ExitReason, ...]


def evaluate_exit_conditions(inputs: ExitInputs) -> ExitDecision:
    """Evaluate all exit conditions and return an ExitDecision.

    Conditions are evaluated in priority order. The first matched condition
    does not short-circuit; all conditions are checked so the operator sees
    every active reason.
    """
    reasons: list[ExitReason] = []

    # --- Override conditions (highest priority) ---
    if inputs.kill_switch_active:
        reasons.append(ExitReason.KILL_SWITCH)
    if inputs.manual_shutdown:
        reasons.append(ExitReason.MANUAL_SHUTDOWN)

    # --- Economic conditions ---
    if inputs.funding_rate_bps <= 0:
        reasons.append(ExitReason.FUNDING_NOT_FAVORABLE)

    if inputs.current_net_edge_bps < inputs.thresholds.min_exit_net_edge_bps:
        reasons.append(ExitReason.NET_EDGE_BELOW_EXIT_THRESHOLD)

    if (
        abs(inputs.current_basis_bps - inputs.entry_basis_bps)
        > inputs.thresholds.max_basis_deterioration_bps
    ):
        reasons.append(ExitReason.BASIS_DETERIORATION)

    # --- Risk conditions ---
    if abs(inputs.pnl.delta_notional_quote) > inputs.thresholds.max_delta_notional_quote:
        reasons.append(ExitReason.DELTA_TOO_LARGE)

    if (
        inputs.evaluated_at - inputs.position.opened_at
    ).total_seconds() >= inputs.thresholds.max_holding_seconds:
        reasons.append(ExitReason.MAX_HOLDING_TIME_REACHED)

    if inputs.pnl.total_pnl_quote <= -inputs.thresholds.stop_loss_quote:
        reasons.append(ExitReason.STOP_LOSS)

    return ExitDecision(
        should_exit=len(reasons) > 0,
        reasons=tuple(reasons),
    )
