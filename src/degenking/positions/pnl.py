"""Paper PnL attribution for hedged positions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from degenking.positions.manager import HedgedPosition


@dataclass(frozen=True, slots=True)
class PositionPnL:
    """PnL attribution in quote currency."""

    symbol: str
    spot_market_value_quote: Decimal
    perp_mark_value_quote: Decimal
    spot_unrealized_pnl_quote: Decimal
    perp_unrealized_pnl_quote: Decimal
    funding_pnl_quote: Decimal
    fees_quote: Decimal
    slippage_quote: Decimal
    total_pnl_quote: Decimal
    delta_quantity: Decimal
    delta_notional_quote: Decimal


def calculate_position_pnl(
    position: HedgedPosition,
    *,
    spot_mid: Decimal,
    perp_mark: Decimal,
) -> PositionPnL:
    """Calculate current paper PnL for a signed spot/perp position."""

    if spot_mid <= 0:
        raise ValueError("spot_mid must be positive")
    if perp_mark <= 0:
        raise ValueError("perp_mark must be positive")

    spot_market_value = position.spot_quantity * spot_mid
    perp_abs_quantity = abs(position.perp_quantity)
    perp_mark_value = perp_abs_quantity * perp_mark
    spot_unrealized = spot_market_value - position.spot_entry_notional_quote
    perp_unrealized = position.perp_entry_notional_quote - perp_mark_value
    total = (
        spot_unrealized
        + perp_unrealized
        + position.funding_pnl_quote
        - position.fees_quote
        - position.slippage_quote
    )

    return PositionPnL(
        symbol=position.symbol,
        spot_market_value_quote=spot_market_value,
        perp_mark_value_quote=perp_mark_value,
        spot_unrealized_pnl_quote=spot_unrealized,
        perp_unrealized_pnl_quote=perp_unrealized,
        funding_pnl_quote=position.funding_pnl_quote,
        fees_quote=position.fees_quote,
        slippage_quote=position.slippage_quote,
        total_pnl_quote=total,
        delta_quantity=position.delta_quantity,
        delta_notional_quote=position.delta_quantity * spot_mid,
    )
