from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.orders.intents import OrderIntent, OrderIntentLeg, OrderSide
from degenking.paper.fill_model import PaperFillResult, PaperFillStatus
from degenking.positions.manager import (
    PositionState,
    add_funding_pnl,
    apply_fill_to_position,
    new_empty_position,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _intent(leg: OrderIntentLeg, side: OrderSide) -> OrderIntent:
    return OrderIntent(
        intent_id=f"intent_{leg.value}",
        trace_id="trace_1",
        run_id="run_1",
        strategy_id="funding_v1",
        config_hash="config_hash",
        idempotency_key=f"idem_{leg.value}",
        symbol="BTCUSDT",
        leg=leg,
        side=side,
        quantity=Decimal("1"),
        notional_quote=Decimal("100"),
        limit_price=Decimal("100"),
        client_order_id=f"client_{leg.value}",
        created_at=NOW,
        updated_at=NOW,
    )


def _fill(quantity: Decimal, notional: Decimal) -> PaperFillResult:
    return PaperFillResult(
        intent_id="intent_1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        status=PaperFillStatus.FULL_FILL,
        filled_quantity=quantity,
        remaining_quantity=Decimal("0"),
        filled_notional_quote=notional,
        average_price=notional / quantity,
        fee_quote=Decimal("0.1"),
        slippage_quote=Decimal("0.2"),
        slippage_bps=Decimal("2"),
        levels_consumed=1,
        fully_filled=True,
    )


def test_apply_spot_and_perp_open_fills_tracks_hedged_delta() -> None:
    position = new_empty_position(symbol="BTCUSDT", opened_at=NOW)
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.SPOT_OPEN, OrderSide.BUY),
        _fill(Decimal("1"), Decimal("100")),
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.PERP_OPEN, OrderSide.SELL),
        _fill(Decimal("1"), Decimal("101")),
        updated_at=NOW,
    )

    assert position.spot_quantity == Decimal("1")
    assert position.perp_quantity == Decimal("-1")
    assert position.delta_quantity == Decimal("0")
    assert position.spot_entry_notional_quote == Decimal("100")
    assert position.perp_entry_notional_quote == Decimal("101")
    assert position.fees_quote == Decimal("0.2")
    assert position.slippage_quote == Decimal("0.4")


def test_apply_close_fills_reduces_position_to_closed() -> None:
    position = new_empty_position(symbol="BTCUSDT", opened_at=NOW)
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.SPOT_OPEN, OrderSide.BUY),
        _fill(Decimal("1"), Decimal("100")),
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.PERP_OPEN, OrderSide.SELL),
        _fill(Decimal("1"), Decimal("100")),
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.SPOT_CLOSE, OrderSide.SELL),
        _fill(Decimal("1"), Decimal("100")),
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        _intent(OrderIntentLeg.PERP_CLOSE, OrderSide.BUY),
        _fill(Decimal("1"), Decimal("100")),
        updated_at=NOW,
    )

    assert position.spot_quantity == Decimal("0")
    assert position.perp_quantity == Decimal("0")
    assert position.state == PositionState.CLOSED


def test_apply_close_rejects_oversized_fill() -> None:
    position = new_empty_position(symbol="BTCUSDT", opened_at=NOW)

    with pytest.raises(ValueError, match="open spot quantity"):
        apply_fill_to_position(
            position,
            _intent(OrderIntentLeg.SPOT_CLOSE, OrderSide.SELL),
            _fill(Decimal("1"), Decimal("100")),
            updated_at=NOW,
        )


def test_add_funding_pnl_accumulates_quote_amount() -> None:
    position = add_funding_pnl(
        new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        funding_pnl_quote=Decimal("2.5"),
        updated_at=NOW,
    )

    assert position.funding_pnl_quote == Decimal("2.5")
