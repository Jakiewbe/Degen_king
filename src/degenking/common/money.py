"""Decimal helpers for monetary calculations."""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0")


def decimal_from_number(value: int | float | str | Decimal) -> Decimal:
    """Convert common numeric inputs to Decimal via string representation."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
