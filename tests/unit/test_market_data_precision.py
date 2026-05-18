"""Tests for Decimal-safe precision and rounding helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from degenking.common.enums import MarketType
from degenking.market_data.models import InstrumentInfo, PrecisionCheckResult
from degenking.market_data.precision import (
    notional,
    round_price_to_tick,
    round_quantity_to_step,
    satisfies_min_notional,
    satisfies_min_quantity,
    validate_order_size,
)

# ---------------------------------------------------------------------------
# Shared instrument fixtures
# ---------------------------------------------------------------------------

BTC_SPOT = InstrumentInfo(
    exchange="binance",
    symbol="BTCUSDT",
    market_type=MarketType.SPOT,
    base_asset="BTC",
    quote_asset="USDT",
    price_tick_size=Decimal("0.01"),
    quantity_step_size=Decimal("0.00001"),
    min_quantity=Decimal("0.00001"),
    min_notional=Decimal("10.00"),
)

ETH_PERP = InstrumentInfo(
    exchange="binance",
    symbol="ETHUSDT",
    market_type=MarketType.PERPETUAL,
    base_asset="ETH",
    quote_asset="USDT",
    price_tick_size=Decimal("0.01"),
    quantity_step_size=Decimal("0.001"),
    min_quantity=Decimal("0.001"),
    min_notional=Decimal("5.00"),
)

NO_MIN_RESTRICTIONS = InstrumentInfo(
    exchange="binance",
    symbol="SOLUSDT",
    market_type=MarketType.SPOT,
    base_asset="SOL",
    quote_asset="USDT",
    price_tick_size=Decimal("0.001"),
    quantity_step_size=Decimal("0.01"),
    min_quantity=None,
    min_notional=None,
)


# ---------------------------------------------------------------------------
# round_price_to_tick
# ---------------------------------------------------------------------------


def test_round_price_down_to_tick() -> None:
    result = round_price_to_tick(Decimal("50000.005"), Decimal("0.01"))
    assert result == Decimal("50000.00")


def test_round_price_exact_tick_unchanged() -> None:
    result = round_price_to_tick(Decimal("50000.00"), Decimal("0.01"))
    assert result == Decimal("50000.00")


def test_round_price_already_multiple_of_tick() -> None:
    result = round_price_to_tick(Decimal("50000.99"), Decimal("0.01"))
    assert result == Decimal("50000.99")


def test_round_price_small_tick_size() -> None:
    result = round_price_to_tick(Decimal("50000.123456789"), Decimal("0.00000001"))
    assert result == Decimal("50000.12345678")


def test_round_price_zero() -> None:
    result = round_price_to_tick(Decimal("0"), Decimal("0.01"))
    assert result == Decimal("0")


def test_round_price_zero_tick_size_raises() -> None:
    with pytest.raises(ValueError, match="tick_size must be positive"):
        round_price_to_tick(Decimal("50000.00"), Decimal("0"))


def test_round_price_negative_tick_size_raises() -> None:
    with pytest.raises(ValueError, match="tick_size must be positive"):
        round_price_to_tick(Decimal("50000.00"), Decimal("-0.01"))


def test_round_price_negative_price_raises() -> None:
    with pytest.raises(ValueError, match="price must be non-negative"):
        round_price_to_tick(Decimal("-50000.00"), Decimal("0.01"))


# ---------------------------------------------------------------------------
# round_quantity_to_step
# ---------------------------------------------------------------------------


def test_round_quantity_down_to_step() -> None:
    result = round_quantity_to_step(Decimal("1.50009"), Decimal("0.001"))
    assert result == Decimal("1.500")


def test_round_quantity_exact_step_unchanged() -> None:
    result = round_quantity_to_step(Decimal("1.500"), Decimal("0.001"))
    assert result == Decimal("1.500")


def test_round_quantity_already_multiple_of_step() -> None:
    result = round_quantity_to_step(Decimal("0.123000"), Decimal("0.001"))
    assert result == Decimal("0.123")


def test_round_quantity_zero() -> None:
    result = round_quantity_to_step(Decimal("0"), Decimal("0.001"))
    assert result == Decimal("0")


def test_round_quantity_zero_step_size_raises() -> None:
    with pytest.raises(ValueError, match="step_size must be positive"):
        round_quantity_to_step(Decimal("1.5"), Decimal("0"))


def test_round_quantity_negative_step_size_raises() -> None:
    with pytest.raises(ValueError, match="step_size must be positive"):
        round_quantity_to_step(Decimal("1.5"), Decimal("-0.001"))


def test_round_quantity_negative_quantity_raises() -> None:
    with pytest.raises(ValueError, match="quantity must be non-negative"):
        round_quantity_to_step(Decimal("-1.5"), Decimal("0.001"))


# ---------------------------------------------------------------------------
# notional
# ---------------------------------------------------------------------------


def test_notional_basic() -> None:
    assert notional(Decimal("50000.00"), Decimal("0.001")) == Decimal("50.00000")


def test_notional_one() -> None:
    assert notional(Decimal("1"), Decimal("1")) == Decimal("1")


def test_notional_zero_quantity() -> None:
    assert notional(Decimal("50000.00"), Decimal("0")) == Decimal("0")


# ---------------------------------------------------------------------------
# satisfies_min_quantity
# ---------------------------------------------------------------------------


def test_satisfies_min_quantity_above() -> None:
    assert satisfies_min_quantity(Decimal("0.001"), Decimal("0.00001")) is True


def test_satisfies_min_quantity_equal() -> None:
    assert satisfies_min_quantity(Decimal("0.00001"), Decimal("0.00001")) is True


def test_satisfies_min_quantity_below() -> None:
    assert satisfies_min_quantity(Decimal("0.000001"), Decimal("0.00001")) is False


def test_satisfies_min_quantity_none_limit() -> None:
    assert satisfies_min_quantity(Decimal("0"), None) is True


def test_satisfies_min_quantity_zero_quantity_none_limit() -> None:
    assert satisfies_min_quantity(Decimal("0"), None) is True


# ---------------------------------------------------------------------------
# satisfies_min_notional
# ---------------------------------------------------------------------------


def test_satisfies_min_notional_above() -> None:
    assert satisfies_min_notional(Decimal("15.00"), Decimal("10.00")) is True


def test_satisfies_min_notional_equal() -> None:
    assert satisfies_min_notional(Decimal("10.00"), Decimal("10.00")) is True


def test_satisfies_min_notional_below() -> None:
    assert satisfies_min_notional(Decimal("5.00"), Decimal("10.00")) is False


def test_satisfies_min_notional_none_limit() -> None:
    assert satisfies_min_notional(Decimal("1.00"), None) is True


# ---------------------------------------------------------------------------
# validate_order_size
# ---------------------------------------------------------------------------


def test_validate_order_size_price_rounded_notional_passes() -> None:
    result = validate_order_size(
        price=Decimal("50000.005"),
        quantity=Decimal("0.001"),
        instrument=BTC_SPOT,
    )

    assert isinstance(result, PrecisionCheckResult)
    assert result.rounded_price == Decimal("50000.00")
    assert result.rounded_quantity == Decimal("0.00100")
    assert result.notional_quote == Decimal("50.0000000")
    assert result.min_quantity_ok is True
    assert result.min_notional_ok is True  # 50.00 >= 10.00
    assert result.passed is True
    assert result.reason is None


def test_validate_order_size_passed_true() -> None:
    result = validate_order_size(
        price=Decimal("50000.00"),
        quantity=Decimal("0.001"),
        instrument=BTC_SPOT,
    )

    assert result.rounded_price == Decimal("50000.00")
    assert result.rounded_quantity == Decimal("0.001")
    assert result.notional_quote == Decimal("50.00000")
    assert result.min_quantity_ok is True
    assert result.min_notional_ok is True
    assert result.passed is True
    assert result.reason is None


def test_validate_order_size_quantity_too_small() -> None:
    result = validate_order_size(
        price=Decimal("50000.00"),
        quantity=Decimal("0.000005"),
        instrument=BTC_SPOT,
    )

    assert result.rounded_quantity == Decimal("0.00000")
    assert result.min_quantity_ok is False
    assert result.min_notional_ok is False
    assert result.passed is False
    assert "min_quantity" in (result.reason or "")


def test_validate_order_size_notional_too_small() -> None:
    result = validate_order_size(
        price=Decimal("100.00"),
        quantity=Decimal("0.00001"),
        instrument=BTC_SPOT,
    )

    assert result.rounded_price == Decimal("100.00")
    assert result.rounded_quantity == Decimal("0.00001")
    assert result.notional_quote == Decimal("0.0010000")
    assert result.min_quantity_ok is True
    assert result.min_notional_ok is False
    assert result.passed is False
    assert "min_notional" in (result.reason or "")


def test_validate_order_size_no_min_restrictions() -> None:
    result = validate_order_size(
        price=Decimal("20.00"),
        quantity=Decimal("0.01"),
        instrument=NO_MIN_RESTRICTIONS,
    )

    assert result.rounded_price == Decimal("20.00")
    assert result.rounded_quantity == Decimal("0.01")
    assert result.min_quantity_ok is True
    assert result.min_notional_ok is True
    assert result.passed is True
    assert result.reason is None


def test_validate_order_size_rounding_always_toward_zero() -> None:
    """Verify that rounding truncates, not bankers-rounding or ceil."""
    result = validate_order_size(
        price=Decimal("50000.009"),  # would round to 50000.01 with ROUND_HALF_UP
        quantity=Decimal("0.001009"),  # would round to 0.00101 with ROUND_HALF_UP
        instrument=BTC_SPOT,
    )

    assert result.rounded_price == Decimal("50000.00")
    assert result.rounded_quantity == Decimal("0.00100")


def test_validate_order_size_eth_perp_passes() -> None:
    result = validate_order_size(
        price=Decimal("3000.00"),
        quantity=Decimal("0.01"),
        instrument=ETH_PERP,
    )

    assert result.rounded_price == Decimal("3000.00")
    assert result.rounded_quantity == Decimal("0.01")
    assert result.notional_quote == Decimal("30.0000")
    assert result.passed is True


def test_validate_order_size_reason_combined() -> None:
    """When both checks fail, reason contains both messages."""
    result = validate_order_size(
        price=Decimal("100.00"),
        quantity=Decimal("0.000005"),
        instrument=BTC_SPOT,
    )

    assert result.min_quantity_ok is False
    assert result.min_notional_ok is False
    assert result.passed is False
    assert result.reason is not None
    assert "min_quantity" in result.reason
    assert "min_notional" in result.reason
    assert ";" in result.reason


def test_validate_order_size_negative_price_propagates_error() -> None:
    with pytest.raises(ValueError, match="price must be non-negative"):
        validate_order_size(
            price=Decimal("-50000.00"),
            quantity=Decimal("0.001"),
            instrument=BTC_SPOT,
        )


def test_validate_order_size_negative_quantity_propagates_error() -> None:
    with pytest.raises(ValueError, match="quantity must be non-negative"):
        validate_order_size(
            price=Decimal("50000.00"),
            quantity=Decimal("-0.001"),
            instrument=BTC_SPOT,
        )
