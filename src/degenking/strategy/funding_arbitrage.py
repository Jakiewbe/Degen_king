"""Pure spot-perpetual funding arbitrage calculations."""

from __future__ import annotations

from decimal import Decimal

from degenking.strategy.models import (
    FundingArbitrageEdge,
    FundingArbitrageInputs,
    FundingArbitrageSignal,
    FundingArbitrageThresholds,
)

BPS = Decimal("10000")


def calculate_edge(inputs: FundingArbitrageInputs) -> FundingArbitrageEdge:
    """Calculate detailed funding-arbitrage edge.

    All quote components are expressed in quote currency. Bps values are
    relative to ``proposed_notional_quote``.
    """

    if inputs.proposed_notional_quote <= 0:
        raise ValueError("proposed_notional_quote must be positive")
    if inputs.spot_mid <= 0:
        raise ValueError("spot_mid must be positive")
    if inputs.perp_mark <= 0:
        raise ValueError("perp_mark must be positive")

    expected_funding_income = inputs.proposed_notional_quote * inputs.funding_rate
    net_edge_quote = (
        expected_funding_income
        - inputs.fees.opening_fees
        - inputs.fees.closing_fees
        - inputs.slippage.entry_slippage
        - inputs.slippage.exit_slippage
        - inputs.buffers.total
    )
    net_edge_bps = net_edge_quote / inputs.proposed_notional_quote * BPS
    funding_rate_bps = inputs.funding_rate * BPS
    basis_bps = (inputs.perp_mark - inputs.spot_mid) / inputs.spot_mid * BPS
    seconds_to_funding = int(
        (inputs.next_funding_time - inputs.evaluated_at).total_seconds()
    )

    return FundingArbitrageEdge(
        expected_funding_income=expected_funding_income,
        opening_fees=inputs.fees.opening_fees,
        closing_fees=inputs.fees.closing_fees,
        entry_slippage=inputs.slippage.entry_slippage,
        exit_slippage=inputs.slippage.exit_slippage,
        funding_uncertainty_buffer=inputs.buffers.funding_uncertainty_buffer,
        basis_adverse_move_buffer=inputs.buffers.basis_adverse_move_buffer,
        residual_delta_buffer=inputs.buffers.residual_delta_buffer,
        net_edge_quote=net_edge_quote,
        net_edge_bps=net_edge_bps,
        funding_rate_bps=funding_rate_bps,
        basis_bps=basis_bps,
        seconds_to_funding=seconds_to_funding,
    )


def evaluate_entry_candidate(
    inputs: FundingArbitrageInputs,
    thresholds: FundingArbitrageThresholds,
) -> FundingArbitrageSignal:
    """Evaluate strategy-level entry conditions for long spot / short perp."""

    edge = calculate_edge(inputs)
    reasons: list[str] = []

    if edge.funding_rate_bps < thresholds.min_funding_rate_bps:
        reasons.append("funding_rate_below_threshold")
    if edge.seconds_to_funding < thresholds.min_seconds_to_funding:
        reasons.append("funding_time_too_close")
    if edge.seconds_to_funding > thresholds.max_seconds_to_funding:
        reasons.append("funding_time_too_far")
    if edge.net_edge_bps < thresholds.min_net_edge_bps:
        reasons.append("net_edge_below_threshold")
    if (
        thresholds.max_basis_bps is not None
        and abs(edge.basis_bps) > thresholds.max_basis_bps
    ):
        reasons.append("basis_exceeds_threshold")

    return FundingArbitrageSignal(
        symbol=inputs.symbol,
        should_enter=not reasons,
        edge=edge,
        reasons=tuple(reasons),
    )
