"""Pure fee and buffer helper functions for funding-arbitrage edge inputs.

No network calls. No side effects. Decimal arithmetic only.
"""

from __future__ import annotations

from decimal import Decimal

from degenking.common.money import ZERO
from degenking.strategy.models import BufferInputs, FeeInputs

BPS_DIVISOR = Decimal("10000")
PCT_DIVISOR = Decimal("100")


def fee_quote(notional_quote: Decimal, fee_bps: Decimal) -> Decimal:
    """Return the fee in quote currency for a given notional and fee rate in bps.

    Raises ValueError if *notional_quote* or *fee_bps* is negative.
    """
    if notional_quote < ZERO:
        raise ValueError(f"notional_quote must be non-negative, got {notional_quote}")
    if fee_bps < ZERO:
        raise ValueError(f"fee_bps must be non-negative, got {fee_bps}")
    return notional_quote * fee_bps / BPS_DIVISOR


def round_trip_fees(
    spot_notional_quote: Decimal,
    perp_notional_quote: Decimal,
    spot_open_fee_bps: Decimal,
    perp_open_fee_bps: Decimal,
    spot_close_fee_bps: Decimal,
    perp_close_fee_bps: Decimal,
) -> FeeInputs:
    """Compute opening and closing fees for both legs of a round-trip.

    Each fee is ``notional * fee_bps / 10000``.
    """
    return FeeInputs(
        spot_open_fee=fee_quote(spot_notional_quote, spot_open_fee_bps),
        perp_open_fee=fee_quote(perp_notional_quote, perp_open_fee_bps),
        spot_close_fee=fee_quote(spot_notional_quote, spot_close_fee_bps),
        perp_close_fee=fee_quote(perp_notional_quote, perp_close_fee_bps),
    )


def notional(price: Decimal, quantity: Decimal) -> Decimal:
    """Return quote notional from price and quantity.

    Raises ValueError if *price* or *quantity* is negative.
    """
    if price < ZERO:
        raise ValueError(f"price must be non-negative, got {price}")
    if quantity < ZERO:
        raise ValueError(f"quantity must be non-negative, got {quantity}")
    return price * quantity


def funding_uncertainty_buffer(
    expected_funding_income: Decimal,
    buffer_pct: Decimal,
) -> Decimal:
    """Return a buffer for funding-rate uncertainty as a percentage of income.

    Raises ValueError if *expected_funding_income* or *buffer_pct* is negative.
    """
    if expected_funding_income < ZERO:
        raise ValueError(
            f"expected_funding_income must be non-negative, got {expected_funding_income}"
        )
    if buffer_pct < ZERO:
        raise ValueError(f"buffer_pct must be non-negative, got {buffer_pct}")
    return expected_funding_income * buffer_pct / PCT_DIVISOR


def basis_adverse_move_buffer(
    notional_quote: Decimal,
    buffer_bps: Decimal,
) -> Decimal:
    """Return a buffer for adverse basis movement, expressed in quote.

    Raises ValueError if *notional_quote* or *buffer_bps* is negative.
    """
    if notional_quote < ZERO:
        raise ValueError(f"notional_quote must be non-negative, got {notional_quote}")
    if buffer_bps < ZERO:
        raise ValueError(f"buffer_bps must be non-negative, got {buffer_bps}")
    return notional_quote * buffer_bps / BPS_DIVISOR


def residual_delta_buffer(
    residual_delta_notional_quote: Decimal,
    buffer_bps: Decimal,
) -> Decimal:
    """Return a buffer for residual delta from lot-size rounding, expressed in quote.

    Raises ValueError if *residual_delta_notional_quote* or *buffer_bps* is negative.
    """
    if residual_delta_notional_quote < ZERO:
        raise ValueError(
            f"residual_delta_notional_quote must be non-negative, "
            f"got {residual_delta_notional_quote}"
        )
    if buffer_bps < ZERO:
        raise ValueError(f"buffer_bps must be non-negative, got {buffer_bps}")
    return residual_delta_notional_quote * buffer_bps / BPS_DIVISOR


def build_buffer_inputs(
    funding_uncertainty: Decimal,
    basis_adverse_move: Decimal,
    residual_delta: Decimal,
) -> BufferInputs:
    """Construct a BufferInputs value from pre-computed buffer amounts.

    Individual buffer values should be computed via the corresponding helpers
    so that validation and unit conventions are enforced at each call site.
    """
    if funding_uncertainty < ZERO:
        raise ValueError(
            f"funding_uncertainty must be non-negative, got {funding_uncertainty}"
        )
    if basis_adverse_move < ZERO:
        raise ValueError(
            f"basis_adverse_move must be non-negative, got {basis_adverse_move}"
        )
    if residual_delta < ZERO:
        raise ValueError(f"residual_delta must be non-negative, got {residual_delta}")
    return BufferInputs(
        funding_uncertainty_buffer=funding_uncertainty,
        basis_adverse_move_buffer=basis_adverse_move,
        residual_delta_buffer=residual_delta,
    )
