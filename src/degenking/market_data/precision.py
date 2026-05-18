"""Decimal-safe precision and rounding helpers for instrument metadata.

Pure functions. No network calls. No side effects.
"""

from __future__ import annotations

from decimal import Decimal

from degenking.common.money import ZERO
from degenking.market_data.models import InstrumentInfo, PrecisionCheckResult


def round_price_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round *price* down to the nearest *tick_size* multiple.

    Raises ValueError if *tick_size* is not positive or *price* is negative.
    """
    if tick_size <= ZERO:
        raise ValueError(f"tick_size must be positive, got {tick_size}")
    if price < ZERO:
        raise ValueError(f"price must be non-negative, got {price}")
    return (price // tick_size) * tick_size


def round_quantity_to_step(quantity: Decimal, step_size: Decimal) -> Decimal:
    """Round *quantity* down to the nearest *step_size* multiple.

    Raises ValueError if *step_size* is not positive or *quantity* is negative.
    """
    if step_size <= ZERO:
        raise ValueError(f"step_size must be positive, got {step_size}")
    if quantity < ZERO:
        raise ValueError(f"quantity must be non-negative, got {quantity}")
    return (quantity // step_size) * step_size


def notional(price: Decimal, quantity: Decimal) -> Decimal:
    """Return the quote notional: ``price * quantity``."""
    return price * quantity


def satisfies_min_quantity(
    quantity: Decimal, min_quantity: Decimal | None
) -> bool:
    """Return True if *quantity* meets or exceeds *min_quantity*.

    A None *min_quantity* is treated as no restriction (always passes).
    """
    if min_quantity is None:
        return True
    return quantity >= min_quantity


def satisfies_min_notional(
    notional_quote: Decimal, min_notional: Decimal | None
) -> bool:
    """Return True if *notional_quote* meets or exceeds *min_notional*.

    A None *min_notional* is treated as no restriction (always passes).
    """
    if min_notional is None:
        return True
    return notional_quote >= min_notional


def validate_order_size(
    price: Decimal,
    quantity: Decimal,
    instrument: InstrumentInfo,
) -> PrecisionCheckResult:
    """Round price and quantity to instrument ticks, then validate against filters.

    Rounding is always toward zero (truncation) for safety.
    Validation checks min_quantity and min_notional from the instrument.

    Returns a ``PrecisionCheckResult`` with the rounded values and pass/fail status.
    """
    rounded_price = round_price_to_tick(price, instrument.price_tick_size)
    rounded_quantity = round_quantity_to_step(quantity, instrument.quantity_step_size)
    notional_quote = notional(rounded_price, rounded_quantity)

    min_qty_ok = satisfies_min_quantity(rounded_quantity, instrument.min_quantity)
    min_not_ok = satisfies_min_notional(notional_quote, instrument.min_notional)
    passed = min_qty_ok and min_not_ok

    reason: str | None = None
    if not passed:
        parts: list[str] = []
        if not min_qty_ok:
            parts.append(
                f"quantity {rounded_quantity} below min_quantity {instrument.min_quantity}"
            )
        if not min_not_ok:
            parts.append(
                f"notional {notional_quote} below min_notional {instrument.min_notional}"
            )
        reason = "; ".join(parts)

    return PrecisionCheckResult(
        rounded_price=rounded_price,
        rounded_quantity=rounded_quantity,
        notional_quote=notional_quote,
        min_quantity_ok=min_qty_ok,
        min_notional_ok=min_not_ok,
        passed=passed,
        reason=reason,
    )
