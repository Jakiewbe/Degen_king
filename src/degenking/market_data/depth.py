"""Order book depth and slippage estimation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot

BPS = Decimal("10000")


class BookSide(StrEnum):
    """Trade direction against an order book."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class SlippageEstimate:
    """Result of walking order book depth for a quote notional."""

    side: BookSide
    requested_notional_quote: Decimal
    filled_notional_quote: Decimal
    filled_quantity: Decimal
    reference_price: Decimal
    average_price: Decimal | None
    slippage_quote: Decimal
    slippage_bps: Decimal
    fully_filled: bool
    levels_consumed: int


def estimate_slippage_for_notional(
    orderbook: OrderBookSnapshot,
    *,
    side: BookSide,
    notional_quote: Decimal,
    reference_price: Decimal | None = None,
) -> SlippageEstimate:
    """Estimate VWAP and slippage by walking one side of an order book.

    Buy orders consume asks. Sell orders consume bids. ``notional_quote`` is the
    target quote value to trade. The result is side-effect free and does not
    create any order intent.
    """

    if notional_quote <= 0:
        raise ValueError("notional_quote must be positive")

    levels = _levels_for_side(orderbook, side)
    inferred_reference = reference_price or _reference_price(orderbook)
    if inferred_reference <= 0:
        raise ValueError("reference_price must be positive")

    remaining_quote = notional_quote
    filled_notional = Decimal("0")
    filled_quantity = Decimal("0")
    levels_consumed = 0

    for level in levels:
        _validate_level(level)
        if remaining_quote <= 0:
            break

        level_notional = level.price * level.quantity
        take_notional = min(remaining_quote, level_notional)
        take_quantity = take_notional / level.price

        filled_notional += take_notional
        filled_quantity += take_quantity
        remaining_quote -= take_notional
        levels_consumed += 1

    fully_filled = remaining_quote <= 0
    average_price = filled_notional / filled_quantity if filled_quantity > 0 else None
    slippage_quote = Decimal("0")
    slippage_bps = Decimal("0")

    if average_price is not None:
        raw_slippage = _signed_slippage_quote(
            side=side,
            reference_price=inferred_reference,
            average_price=average_price,
            quantity=filled_quantity,
        )
        slippage_quote = max(raw_slippage, Decimal("0"))
        slippage_bps = (
            slippage_quote / filled_notional * BPS
            if filled_notional > 0
            else Decimal("0")
        )

    return SlippageEstimate(
        side=side,
        requested_notional_quote=notional_quote,
        filled_notional_quote=filled_notional,
        filled_quantity=filled_quantity,
        reference_price=inferred_reference,
        average_price=average_price,
        slippage_quote=slippage_quote,
        slippage_bps=slippage_bps,
        fully_filled=fully_filled,
        levels_consumed=levels_consumed,
    )


def has_min_depth(
    orderbook: OrderBookSnapshot,
    *,
    side: BookSide,
    min_depth_quote: Decimal,
) -> bool:
    """Return whether one side of the book has at least ``min_depth_quote``."""

    if min_depth_quote < 0:
        raise ValueError("min_depth_quote must be non-negative")
    levels = _levels_for_side(orderbook, side)
    depth = sum((level.price * level.quantity for level in levels), Decimal("0"))
    return depth >= min_depth_quote


def _levels_for_side(
    orderbook: OrderBookSnapshot,
    side: BookSide,
) -> tuple[OrderBookLevel, ...]:
    if side == BookSide.BUY:
        return orderbook.asks
    if side == BookSide.SELL:
        return orderbook.bids
    raise ValueError(f"unsupported book side: {side}")


def _reference_price(orderbook: OrderBookSnapshot) -> Decimal:
    if not orderbook.bids or not orderbook.asks:
        raise ValueError(
            "orderbook requires at least one bid and one ask for reference price"
        )
    best_bid = orderbook.bids[0].price
    best_ask = orderbook.asks[0].price
    if best_bid <= 0 or best_ask <= 0:
        raise ValueError("best bid and ask must be positive")
    return (best_bid + best_ask) / Decimal("2")


def _validate_level(level: OrderBookLevel) -> None:
    if level.price <= 0:
        raise ValueError("orderbook level price must be positive")
    if level.quantity < 0:
        raise ValueError("orderbook level quantity must be non-negative")


def _signed_slippage_quote(
    *,
    side: BookSide,
    reference_price: Decimal,
    average_price: Decimal,
    quantity: Decimal,
) -> Decimal:
    if side == BookSide.BUY:
        return (average_price - reference_price) * quantity
    return (reference_price - average_price) * quantity
