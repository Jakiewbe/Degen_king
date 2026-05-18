from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from degenking.strategy.funding_arbitrage import calculate_edge, evaluate_entry_candidate
from degenking.strategy.models import (
    BufferInputs,
    FeeInputs,
    FundingArbitrageInputs,
    FundingArbitrageThresholds,
    SlippageInputs,
)

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _inputs(
    *,
    funding_rate: Decimal = Decimal("0.001"),
    next_funding_delta: timedelta = timedelta(hours=2),
    perp_mark: Decimal = Decimal("100.10"),
) -> FundingArbitrageInputs:
    return FundingArbitrageInputs(
        symbol="BTCUSDT",
        proposed_notional_quote=Decimal("10000"),
        funding_rate=funding_rate,
        next_funding_time=NOW + next_funding_delta,
        evaluated_at=NOW,
        spot_mid=Decimal("100"),
        perp_mark=perp_mark,
        fees=FeeInputs(
            spot_open_fee=Decimal("2"),
            perp_open_fee=Decimal("2"),
            spot_close_fee=Decimal("2"),
            perp_close_fee=Decimal("2"),
        ),
        slippage=SlippageInputs(
            spot_entry_slippage=Decimal("1"),
            perp_entry_slippage=Decimal("1"),
            spot_exit_slippage=Decimal("1"),
            perp_exit_slippage=Decimal("1"),
        ),
        buffers=BufferInputs(
            funding_uncertainty_buffer=Decimal("1"),
            basis_adverse_move_buffer=Decimal("1"),
            residual_delta_buffer=Decimal("1"),
        ),
    )


def _thresholds() -> FundingArbitrageThresholds:
    return FundingArbitrageThresholds(
        min_net_edge_bps=Decimal("1"),
        min_funding_rate_bps=Decimal("5"),
        min_seconds_to_funding=900,
        max_seconds_to_funding=25200,
        max_basis_bps=Decimal("75"),
    )


def test_calculate_edge_in_quote_and_bps() -> None:
    edge = calculate_edge(_inputs())

    assert edge.expected_funding_income == Decimal("10.000")
    assert edge.opening_fees == Decimal("4")
    assert edge.closing_fees == Decimal("4")
    assert edge.entry_slippage == Decimal("2")
    assert edge.exit_slippage == Decimal("2")
    assert edge.funding_uncertainty_buffer == Decimal("1")
    assert edge.basis_adverse_move_buffer == Decimal("1")
    assert edge.residual_delta_buffer == Decimal("1")
    assert edge.net_edge_quote == Decimal("-5.000")
    assert edge.net_edge_bps == Decimal("-5.0000")
    assert edge.funding_rate_bps == Decimal("10.000")
    assert edge.basis_bps == Decimal("10.0000")
    assert edge.seconds_to_funding == 7200


def test_entry_candidate_passes_when_thresholds_are_met() -> None:
    inputs = _inputs(funding_rate=Decimal("0.003"))

    signal = evaluate_entry_candidate(inputs, _thresholds())

    assert signal.should_enter is True
    assert signal.reasons == ()
    assert signal.edge.net_edge_bps == Decimal("15.0000")


def test_entry_candidate_rejects_low_funding_rate() -> None:
    signal = evaluate_entry_candidate(_inputs(funding_rate=Decimal("0.0001")), _thresholds())

    assert signal.should_enter is False
    assert "funding_rate_below_threshold" in signal.reasons


def test_entry_candidate_rejects_time_too_close() -> None:
    signal = evaluate_entry_candidate(
        _inputs(funding_rate=Decimal("0.003"), next_funding_delta=timedelta(minutes=5)),
        _thresholds(),
    )

    assert signal.should_enter is False
    assert "funding_time_too_close" in signal.reasons


def test_entry_candidate_rejects_time_too_far() -> None:
    signal = evaluate_entry_candidate(
        _inputs(funding_rate=Decimal("0.003"), next_funding_delta=timedelta(hours=8)),
        _thresholds(),
    )

    assert signal.should_enter is False
    assert "funding_time_too_far" in signal.reasons


def test_entry_candidate_rejects_negative_net_edge() -> None:
    signal = evaluate_entry_candidate(_inputs(), _thresholds())

    assert signal.should_enter is False
    assert "net_edge_below_threshold" in signal.reasons


def test_entry_candidate_rejects_large_basis() -> None:
    signal = evaluate_entry_candidate(
        _inputs(funding_rate=Decimal("0.003"), perp_mark=Decimal("101")),
        _thresholds(),
    )

    assert signal.should_enter is False
    assert "basis_exceeds_threshold" in signal.reasons


def test_calculate_edge_rejects_invalid_notional() -> None:
    inputs = _inputs()
    invalid = FundingArbitrageInputs(
        symbol=inputs.symbol,
        proposed_notional_quote=Decimal("0"),
        funding_rate=inputs.funding_rate,
        next_funding_time=inputs.next_funding_time,
        evaluated_at=inputs.evaluated_at,
        spot_mid=inputs.spot_mid,
        perp_mark=inputs.perp_mark,
        fees=inputs.fees,
        slippage=inputs.slippage,
        buffers=inputs.buffers,
    )

    with pytest.raises(ValueError, match="proposed_notional_quote"):
        calculate_edge(invalid)
