"""Deterministic paper fill model.

The fill model walks an in-memory order book and returns simulated fill data.
It does not submit orders, mutate positions, or call any exchange API.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from degenking.market_data.depth import BPS, BookSide
from degenking.market_data.models import OrderBookLevel, OrderBookSnapshot
from degenking.orders.intents import OrderIntent, OrderSide
from degenking.strategy.costs import fee_quote


class PaperFillStatus(StrEnum):
    """Paper fill outcome."""

    NO_FILL = "no_fill"
    PARTIAL_FILL = "partial_fill"
    FULL_FILL = "full_fill"


@dataclass(frozen=True, slots=True)
class PaperFillResult:
    """Result of applying one paper intent to one order book snapshot."""

    intent_id: str
    symbol: str
    side: OrderSide
    status: PaperFillStatus
    filled_quantity: Decimal
    remaining_quantity: Decimal
    filled_notional_quote: Decimal
    average_price: Decimal | None
    fee_quote: Decimal
    slippage_quote: Decimal
    slippage_bps: Decimal
    levels_consumed: int
    fully_filled: bool


def simulate_limit_fill(
    intent: OrderIntent,
    orderbook: OrderBookSnapshot,
    *,
    taker_fee_bps: Decimal,
    fill_ratio: Decimal = Decimal("1"),
    reference_price: Decimal | None = None,
) -> PaperFillResult:
    """Simulate a taker-style limit fill against current order book depth.

    ``fill_ratio`` is a deterministic throttle used by tests and future paper
    scenarios to force partial fills without randomness.
    """

    if orderbook.symbol != intent.symbol:
        raise ValueError("orderbook symbol must match intent symbol")
    if taker_fee_bps < 0:
        raise ValueError("taker_fee_bps must be non-negative")
    if not (Decimal("0") < fill_ratio <= Decimal("1")):
        raise ValueError("fill_ratio must be in the range (0, 1]")

    target_quantity = intent.quantity * fill_ratio
    levels = _fillable_levels(orderbook, intent.side, intent.limit_price)
    reference = reference_price or _reference_price(orderbook)

    filled_quantity = Decimal("0")
    filled_notional_quote = Decimal("0")
    levels_consumed = 0

    for level in levels:
        if filled_quantity >= target_quantity:
            break
        remaining_quantity = target_quantity - filled_quantity
        take_quantity = min(remaining_quantity, level.quantity)
        if take_quantity <= 0:
            continue
        filled_quantity += take_quantity
        filled_notional_quote += take_quantity * level.price
        levels_consumed += 1

    average_price = (
        filled_notional_quote / filled_quantity if filled_quantity > 0 else None
    )
    status = _status(filled_quantity, intent.quantity)
    slippage_quote = Decimal("0")
    slippage_bps = Decimal("0")

    if average_price is not None:
        raw_slippage = _signed_slippage_quote(
            side=BookSide(intent.side.value),
            reference_price=reference,
            average_price=average_price,
            quantity=filled_quantity,
        )
        slippage_quote = max(raw_slippage, Decimal("0"))
        slippage_bps = (
            slippage_quote / filled_notional_quote * BPS
            if filled_notional_quote > 0
            else Decimal("0")
        )

    return PaperFillResult(
        intent_id=intent.intent_id,
        symbol=intent.symbol,
        side=intent.side,
        status=status,
        filled_quantity=filled_quantity,
        remaining_quantity=intent.quantity - filled_quantity,
        filled_notional_quote=filled_notional_quote,
        average_price=average_price,
        fee_quote=fee_quote(filled_notional_quote, taker_fee_bps),
        slippage_quote=slippage_quote,
        slippage_bps=slippage_bps,
        levels_consumed=levels_consumed,
        fully_filled=status == PaperFillStatus.FULL_FILL,
    )


def _fillable_levels(
    orderbook: OrderBookSnapshot,
    side: OrderSide,
    limit_price: Decimal,
) -> tuple[OrderBookLevel, ...]:
    if side == OrderSide.BUY:
        return tuple(level for level in orderbook.asks if level.price <= limit_price)
    if side == OrderSide.SELL:
        return tuple(level for level in orderbook.bids if level.price >= limit_price)
    raise ValueError(f"unsupported order side: {side}")


def _reference_price(orderbook: OrderBookSnapshot) -> Decimal:
    if not orderbook.bids or not orderbook.asks:
        raise ValueError("orderbook requires at least one bid and ask")
    best_bid = orderbook.bids[0].price
    best_ask = orderbook.asks[0].price
    if best_bid <= 0 or best_ask <= 0:
        raise ValueError("best bid and ask must be positive")
    return (best_bid + best_ask) / Decimal("2")


def _status(filled_quantity: Decimal, requested_quantity: Decimal) -> PaperFillStatus:
    if filled_quantity <= 0:
        return PaperFillStatus.NO_FILL
    if filled_quantity < requested_quantity:
        return PaperFillStatus.PARTIAL_FILL
    return PaperFillStatus.FULL_FILL


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
