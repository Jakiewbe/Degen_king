from __future__ import annotations

from degenking.common.enums import RuntimeMode
from degenking.orders.idempotency import (
    CLIENT_ORDER_ID_MAX_LENGTH,
    IdempotencyLedger,
    build_client_order_id,
    build_idempotency_key,
)
from degenking.orders.intents import OrderIntentLeg, OrderSide


def test_idempotency_key_is_stable_for_same_logical_action() -> None:
    first = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        logical_action_id="signal_1",
    )
    second = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        logical_action_id="signal_1",
    )

    assert first == second
    assert first.startswith("idem_")


def test_idempotency_key_changes_for_different_leg() -> None:
    spot = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        logical_action_id="signal_1",
    )
    perp = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.PERP_OPEN,
        side=OrderSide.SELL,
        logical_action_id="signal_1",
    )

    assert spot != perp


def test_client_order_id_is_deterministic_and_length_limited() -> None:
    idempotency_key = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        logical_action_id="signal_1",
    )

    client_order_id = build_client_order_id(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        idempotency_key=idempotency_key,
    )

    assert len(client_order_id) <= CLIENT_ORDER_ID_MAX_LENGTH
    assert client_order_id == build_client_order_id(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        idempotency_key=idempotency_key,
    )


def test_idempotency_ledger_suppresses_duplicates() -> None:
    ledger = IdempotencyLedger()

    assert ledger.register("idem_1") is True
    assert ledger.register("idem_1") is False
