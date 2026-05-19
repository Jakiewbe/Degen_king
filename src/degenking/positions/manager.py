"""Deterministic paper position updates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from degenking.orders.intents import OrderIntent, OrderIntentLeg
from degenking.paper.fill_model import PaperFillResult


class PositionState(StrEnum):
    """Paper position lifecycle."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class HedgedPosition:
    """Signed paper position for one spot/perp hedge.

    Spot quantity is positive when long. Perp quantity is negative when short.
    Entry notionals are stored as positive quote values for the open quantities.
    """

    symbol: str
    spot_quantity: Decimal
    perp_quantity: Decimal
    spot_entry_notional_quote: Decimal
    perp_entry_notional_quote: Decimal
    fees_quote: Decimal
    slippage_quote: Decimal
    funding_pnl_quote: Decimal
    opened_at: datetime
    updated_at: datetime
    state: PositionState = PositionState.OPEN

    @property
    def delta_quantity(self) -> Decimal:
        """Net signed base quantity."""

        return self.spot_quantity + self.perp_quantity

    @property
    def is_flat(self) -> bool:
        """Whether both legs have no remaining quantity."""

        return self.spot_quantity == 0 and self.perp_quantity == 0


def new_empty_position(
    *,
    symbol: str,
    opened_at: datetime,
) -> HedgedPosition:
    """Create an empty paper position accumulator for one symbol."""

    return HedgedPosition(
        symbol=symbol,
        spot_quantity=Decimal("0"),
        perp_quantity=Decimal("0"),
        spot_entry_notional_quote=Decimal("0"),
        perp_entry_notional_quote=Decimal("0"),
        fees_quote=Decimal("0"),
        slippage_quote=Decimal("0"),
        funding_pnl_quote=Decimal("0"),
        opened_at=opened_at,
        updated_at=opened_at,
    )


def apply_fill_to_position(
    position: HedgedPosition,
    intent: OrderIntent,
    fill: PaperFillResult,
    *,
    updated_at: datetime,
) -> HedgedPosition:
    """Apply one paper fill to a position accumulator."""

    if position.symbol != intent.symbol or fill.symbol != intent.symbol:
        raise ValueError("position, intent, and fill symbols must match")
    if fill.filled_quantity <= 0:
        return replace(position, updated_at=updated_at)

    spot_quantity = position.spot_quantity
    perp_quantity = position.perp_quantity
    spot_entry_notional = position.spot_entry_notional_quote
    perp_entry_notional = position.perp_entry_notional_quote

    if intent.leg == OrderIntentLeg.SPOT_OPEN:
        spot_quantity += fill.filled_quantity
        spot_entry_notional += fill.filled_notional_quote
    elif intent.leg == OrderIntentLeg.PERP_OPEN:
        perp_quantity -= fill.filled_quantity
        perp_entry_notional += fill.filled_notional_quote
    elif intent.leg == OrderIntentLeg.SPOT_CLOSE:
        spot_quantity = _reduce_toward_zero(spot_quantity, fill.filled_quantity)
        spot_entry_notional = _reduce_notional(
            spot_entry_notional,
            position.spot_quantity,
            fill.filled_quantity,
        )
    elif intent.leg == OrderIntentLeg.PERP_CLOSE:
        perp_quantity = _increase_short_toward_zero(perp_quantity, fill.filled_quantity)
        perp_entry_notional = _reduce_notional(
            perp_entry_notional,
            abs(position.perp_quantity),
            fill.filled_quantity,
        )
    elif intent.leg == OrderIntentLeg.CLEANUP:
        spot_quantity, perp_quantity = _apply_cleanup(
            spot_quantity,
            perp_quantity,
            fill.filled_quantity,
        )
    else:
        raise ValueError(f"unsupported intent leg: {intent.leg}")

    state = (
        PositionState.CLOSED
        if spot_quantity == 0 and perp_quantity == 0
        else PositionState.OPEN
    )
    return replace(
        position,
        spot_quantity=spot_quantity,
        perp_quantity=perp_quantity,
        spot_entry_notional_quote=spot_entry_notional,
        perp_entry_notional_quote=perp_entry_notional,
        fees_quote=position.fees_quote + fill.fee_quote,
        slippage_quote=position.slippage_quote + fill.slippage_quote,
        updated_at=updated_at,
        state=state,
    )


def add_funding_pnl(
    position: HedgedPosition,
    *,
    funding_pnl_quote: Decimal,
    updated_at: datetime,
) -> HedgedPosition:
    """Add a funding settlement amount to a paper position."""

    return replace(
        position,
        funding_pnl_quote=position.funding_pnl_quote + funding_pnl_quote,
        updated_at=updated_at,
    )


def _reduce_toward_zero(quantity: Decimal, reduction: Decimal) -> Decimal:
    if reduction > quantity:
        raise ValueError("close fill cannot exceed open spot quantity")
    return quantity - reduction


def _increase_short_toward_zero(quantity: Decimal, reduction: Decimal) -> Decimal:
    if quantity >= 0:
        raise ValueError("perp close requires an open short quantity")
    if reduction > abs(quantity):
        raise ValueError("close fill cannot exceed open perp quantity")
    return quantity + reduction


def _reduce_notional(
    entry_notional: Decimal,
    open_quantity: Decimal,
    reduction: Decimal,
) -> Decimal:
    if open_quantity <= 0:
        raise ValueError("open_quantity must be positive when reducing notional")
    remaining_ratio = (open_quantity - reduction) / open_quantity
    return entry_notional * remaining_ratio


def _apply_cleanup(
    spot_quantity: Decimal,
    perp_quantity: Decimal,
    cleanup_quantity: Decimal,
) -> tuple[Decimal, Decimal]:
    if spot_quantity > abs(perp_quantity):
        return spot_quantity - cleanup_quantity, perp_quantity
    if abs(perp_quantity) > spot_quantity:
        return spot_quantity, perp_quantity + cleanup_quantity
    return spot_quantity, perp_quantity
