"""Tests for fee and buffer helper functions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from degenking.strategy.costs import (
    basis_adverse_move_buffer,
    build_buffer_inputs,
    fee_quote,
    funding_uncertainty_buffer,
    notional,
    residual_delta_buffer,
    round_trip_fees,
)
from degenking.strategy.models import BufferInputs, FeeInputs

# ---------------------------------------------------------------------------
# fee_quote
# ---------------------------------------------------------------------------


def test_fee_quote_basic() -> None:
    result = fee_quote(Decimal("10000"), Decimal("10"))
    assert result == Decimal("10")


def test_fee_quote_zero_bps() -> None:
    result = fee_quote(Decimal("10000"), Decimal("0"))
    assert result == Decimal("0")


def test_fee_quote_zero_notional() -> None:
    result = fee_quote(Decimal("0"), Decimal("10"))
    assert result == Decimal("0")


def test_fee_quote_fractional_bps() -> None:
    result = fee_quote(Decimal("50000"), Decimal("7.5"))
    assert result == Decimal("37.5")


def test_fee_quote_large_notional() -> None:
    result = fee_quote(Decimal("1000000"), Decimal("1"))
    assert result == Decimal("100")


def test_fee_quote_negative_notional_raises() -> None:
    with pytest.raises(ValueError, match="notional_quote must be non-negative"):
        fee_quote(Decimal("-1"), Decimal("10"))


def test_fee_quote_negative_bps_raises() -> None:
    with pytest.raises(ValueError, match="fee_bps must be non-negative"):
        fee_quote(Decimal("10000"), Decimal("-10"))


# ---------------------------------------------------------------------------
# round_trip_fees
# ---------------------------------------------------------------------------


def test_round_trip_fees_all_components() -> None:
    result = round_trip_fees(
        spot_notional_quote=Decimal("50000"),
        perp_notional_quote=Decimal("50000"),
        spot_open_fee_bps=Decimal("1"),
        perp_open_fee_bps=Decimal("2"),
        spot_close_fee_bps=Decimal("1"),
        perp_close_fee_bps=Decimal("2"),
    )

    assert isinstance(result, FeeInputs)
    assert result.spot_open_fee == Decimal("5")
    assert result.perp_open_fee == Decimal("10")
    assert result.spot_close_fee == Decimal("5")
    assert result.perp_close_fee == Decimal("10")
    assert result.opening_fees == Decimal("15")
    assert result.closing_fees == Decimal("15")


def test_round_trip_fees_zero_rates() -> None:
    result = round_trip_fees(
        spot_notional_quote=Decimal("50000"),
        perp_notional_quote=Decimal("50000"),
        spot_open_fee_bps=Decimal("0"),
        perp_open_fee_bps=Decimal("0"),
        spot_close_fee_bps=Decimal("0"),
        perp_close_fee_bps=Decimal("0"),
    )

    assert result.spot_open_fee == Decimal("0")
    assert result.perp_open_fee == Decimal("0")
    assert result.spot_close_fee == Decimal("0")
    assert result.perp_close_fee == Decimal("0")
    assert result.opening_fees == Decimal("0")
    assert result.closing_fees == Decimal("0")


def test_round_trip_fees_different_notionals() -> None:
    result = round_trip_fees(
        spot_notional_quote=Decimal("50000"),
        perp_notional_quote=Decimal("49990"),
        spot_open_fee_bps=Decimal("10"),
        perp_open_fee_bps=Decimal("10"),
        spot_close_fee_bps=Decimal("10"),
        perp_close_fee_bps=Decimal("10"),
    )

    assert result.spot_open_fee == Decimal("50")
    assert result.perp_open_fee == Decimal("49.990")
    assert result.spot_close_fee == Decimal("50")
    assert result.perp_close_fee == Decimal("49.990")


def test_round_trip_fees_negative_notional_propagates() -> None:
    with pytest.raises(ValueError, match="notional_quote must be non-negative"):
        round_trip_fees(
            spot_notional_quote=Decimal("-1"),
            perp_notional_quote=Decimal("50000"),
            spot_open_fee_bps=Decimal("1"),
            perp_open_fee_bps=Decimal("1"),
            spot_close_fee_bps=Decimal("1"),
            perp_close_fee_bps=Decimal("1"),
        )


def test_round_trip_fees_negative_bps_propagates() -> None:
    with pytest.raises(ValueError, match="fee_bps must be non-negative"):
        round_trip_fees(
            spot_notional_quote=Decimal("50000"),
            perp_notional_quote=Decimal("50000"),
            spot_open_fee_bps=Decimal("-1"),
            perp_open_fee_bps=Decimal("1"),
            spot_close_fee_bps=Decimal("1"),
            perp_close_fee_bps=Decimal("1"),
        )


# ---------------------------------------------------------------------------
# notional
# ---------------------------------------------------------------------------


def test_notional_basic() -> None:
    assert notional(Decimal("50000"), Decimal("0.001")) == Decimal("50.000")


def test_notional_zero_price() -> None:
    assert notional(Decimal("0"), Decimal("1")) == Decimal("0")


def test_notional_zero_quantity() -> None:
    assert notional(Decimal("50000"), Decimal("0")) == Decimal("0")


def test_notional_negative_price_raises() -> None:
    with pytest.raises(ValueError, match="price must be non-negative"):
        notional(Decimal("-1"), Decimal("1"))


def test_notional_negative_quantity_raises() -> None:
    with pytest.raises(ValueError, match="quantity must be non-negative"):
        notional(Decimal("1"), Decimal("-1"))


# ---------------------------------------------------------------------------
# funding_uncertainty_buffer
# ---------------------------------------------------------------------------


def test_funding_uncertainty_buffer_basic() -> None:
    result = funding_uncertainty_buffer(Decimal("100"), Decimal("10"))
    assert result == Decimal("10")


def test_funding_uncertainty_buffer_zero_pct() -> None:
    result = funding_uncertainty_buffer(Decimal("100"), Decimal("0"))
    assert result == Decimal("0")


def test_funding_uncertainty_buffer_zero_income() -> None:
    result = funding_uncertainty_buffer(Decimal("0"), Decimal("10"))
    assert result == Decimal("0")


def test_funding_uncertainty_buffer_fractional_pct() -> None:
    result = funding_uncertainty_buffer(Decimal("50"), Decimal("12.5"))
    assert result == Decimal("6.25")


def test_funding_uncertainty_buffer_negative_income_raises() -> None:
    with pytest.raises(ValueError, match="expected_funding_income must be non-negative"):
        funding_uncertainty_buffer(Decimal("-1"), Decimal("10"))


def test_funding_uncertainty_buffer_negative_pct_raises() -> None:
    with pytest.raises(ValueError, match="buffer_pct must be non-negative"):
        funding_uncertainty_buffer(Decimal("100"), Decimal("-10"))


# ---------------------------------------------------------------------------
# basis_adverse_move_buffer
# ---------------------------------------------------------------------------


def test_basis_adverse_move_buffer_basic() -> None:
    result = basis_adverse_move_buffer(Decimal("50000"), Decimal("5"))
    assert result == Decimal("25")


def test_basis_adverse_move_buffer_zero_bps() -> None:
    result = basis_adverse_move_buffer(Decimal("50000"), Decimal("0"))
    assert result == Decimal("0")


def test_basis_adverse_move_buffer_fractional_bps() -> None:
    result = basis_adverse_move_buffer(Decimal("50000"), Decimal("2.5"))
    assert result == Decimal("12.5")


def test_basis_adverse_move_buffer_negative_notional_raises() -> None:
    with pytest.raises(ValueError, match="notional_quote must be non-negative"):
        basis_adverse_move_buffer(Decimal("-1"), Decimal("5"))


def test_basis_adverse_move_buffer_negative_bps_raises() -> None:
    with pytest.raises(ValueError, match="buffer_bps must be non-negative"):
        basis_adverse_move_buffer(Decimal("50000"), Decimal("-5"))


# ---------------------------------------------------------------------------
# residual_delta_buffer
# ---------------------------------------------------------------------------


def test_residual_delta_buffer_basic() -> None:
    result = residual_delta_buffer(Decimal("1000"), Decimal("3"))
    assert result == Decimal("0.3")


def test_residual_delta_buffer_zero_bps() -> None:
    result = residual_delta_buffer(Decimal("1000"), Decimal("0"))
    assert result == Decimal("0")


def test_residual_delta_buffer_fractional_bps() -> None:
    result = residual_delta_buffer(Decimal("500"), Decimal("1.5"))
    assert result == Decimal("0.075")


def test_residual_delta_buffer_negative_notional_raises() -> None:
    with pytest.raises(
        ValueError, match="residual_delta_notional_quote must be non-negative"
    ):
        residual_delta_buffer(Decimal("-1"), Decimal("3"))


def test_residual_delta_buffer_negative_bps_raises() -> None:
    with pytest.raises(ValueError, match="buffer_bps must be non-negative"):
        residual_delta_buffer(Decimal("1000"), Decimal("-3"))


# ---------------------------------------------------------------------------
# build_buffer_inputs
# ---------------------------------------------------------------------------


def test_build_buffer_inputs_constructs() -> None:
    result = build_buffer_inputs(
        funding_uncertainty=Decimal("10"),
        basis_adverse_move=Decimal("25"),
        residual_delta=Decimal("0.3"),
    )

    assert isinstance(result, BufferInputs)
    assert result.funding_uncertainty_buffer == Decimal("10")
    assert result.basis_adverse_move_buffer == Decimal("25")
    assert result.residual_delta_buffer == Decimal("0.3")
    assert result.total == Decimal("35.3")


def test_build_buffer_inputs_all_zeros() -> None:
    result = build_buffer_inputs(
        funding_uncertainty=Decimal("0"),
        basis_adverse_move=Decimal("0"),
        residual_delta=Decimal("0"),
    )

    assert result.total == Decimal("0")


def test_build_buffer_inputs_negative_funding_buffer_raises() -> None:
    with pytest.raises(ValueError, match="funding_uncertainty"):
        build_buffer_inputs(
            funding_uncertainty=Decimal("-1"),
            basis_adverse_move=Decimal("0"),
            residual_delta=Decimal("0"),
        )


def test_build_buffer_inputs_negative_basis_buffer_raises() -> None:
    with pytest.raises(ValueError, match="basis_adverse_move"):
        build_buffer_inputs(
            funding_uncertainty=Decimal("0"),
            basis_adverse_move=Decimal("-1"),
            residual_delta=Decimal("0"),
        )


def test_build_buffer_inputs_negative_delta_buffer_raises() -> None:
    with pytest.raises(ValueError, match="residual_delta"):
        build_buffer_inputs(
            funding_uncertainty=Decimal("0"),
            basis_adverse_move=Decimal("0"),
            residual_delta=Decimal("-1"),
        )


def test_build_buffer_inputs_integration_with_helpers() -> None:
    """End-to-end: compute buffers via helpers, then build BufferInputs."""
    funding_unc = funding_uncertainty_buffer(Decimal("100"), Decimal("10"))
    basis_buf = basis_adverse_move_buffer(Decimal("50000"), Decimal("5"))
    delta_buf = residual_delta_buffer(Decimal("1000"), Decimal("3"))

    result = build_buffer_inputs(
        funding_uncertainty=funding_unc,
        basis_adverse_move=basis_buf,
        residual_delta=delta_buf,
    )

    assert result.funding_uncertainty_buffer == Decimal("10")
    assert result.basis_adverse_move_buffer == Decimal("25")
    assert result.residual_delta_buffer == Decimal("0.3")
    assert result.total == Decimal("35.3")
