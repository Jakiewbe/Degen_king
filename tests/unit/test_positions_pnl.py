from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.positions.manager import HedgedPosition
from degenking.positions.pnl import calculate_position_pnl

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _position() -> HedgedPosition:
    return HedgedPosition(
        symbol="BTCUSDT",
        spot_quantity=Decimal("1"),
        perp_quantity=Decimal("-1"),
        spot_entry_notional_quote=Decimal("100"),
        perp_entry_notional_quote=Decimal("101"),
        fees_quote=Decimal("0.2"),
        slippage_quote=Decimal("0.3"),
        funding_pnl_quote=Decimal("1.5"),
        opened_at=NOW,
        updated_at=NOW,
    )


def test_calculate_position_pnl_for_hedged_position() -> None:
    pnl = calculate_position_pnl(
        _position(),
        spot_mid=Decimal("102"),
        perp_mark=Decimal("100"),
    )

    assert pnl.spot_market_value_quote == Decimal("102")
    assert pnl.perp_mark_value_quote == Decimal("100")
    assert pnl.spot_unrealized_pnl_quote == Decimal("2")
    assert pnl.perp_unrealized_pnl_quote == Decimal("1")
    assert pnl.total_pnl_quote == Decimal("4.0")
    assert pnl.delta_quantity == Decimal("0")
    assert pnl.delta_notional_quote == Decimal("0")


def test_calculate_position_pnl_rejects_invalid_prices() -> None:
    with pytest.raises(ValueError, match="spot_mid"):
        calculate_position_pnl(_position(), spot_mid=Decimal("0"), perp_mark=Decimal("1"))
