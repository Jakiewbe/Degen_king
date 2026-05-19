from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.fill_model import PaperFillResult, PaperFillStatus
from degenking.positions.manager import apply_fill_to_position, new_empty_position
from degenking.reconciliation.service import (
    ReconciliationDiscrepancyType,
    ReconciliationStatus,
    reconcile_paper_state,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _intent(
    *,
    intent_id: str = "intent_spot_open",
    leg: OrderIntentLeg = OrderIntentLeg.SPOT_OPEN,
    side: OrderSide = OrderSide.BUY,
    state: OrderIntentState = OrderIntentState.FILLED,
    filled_quantity: Decimal = Decimal("1"),
    symbol: str = "BTCUSDT",
) -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id,
        trace_id="trace_1",
        run_id="run_1",
        strategy_id="funding_v1",
        config_hash="config_hash",
        idempotency_key=f"idem_{intent_id}",
        symbol=symbol,
        leg=leg,
        side=side,
        quantity=Decimal("1"),
        notional_quote=Decimal("100"),
        limit_price=Decimal("100"),
        client_order_id=f"client_{intent_id}",
        created_at=NOW,
        updated_at=NOW,
        state=state,
        filled_quantity=filled_quantity,
    )


def _fill(
    *,
    intent_id: str = "intent_spot_open",
    quantity: Decimal = Decimal("1"),
    notional: Decimal = Decimal("100"),
    side: OrderSide = OrderSide.BUY,
    symbol: str = "BTCUSDT",
) -> PaperFillResult:
    return PaperFillResult(
        intent_id=intent_id,
        symbol=symbol,
        side=side,
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


def test_reconcile_clean_paper_state() -> None:
    intent = _intent()
    fill = _fill()
    observed_position = apply_fill_to_position(
        new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        intent,
        fill,
        updated_at=NOW,
    )

    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(intent,),
        fills=(fill,),
        observed_position=observed_position,
        reconciled_at=NOW,
    )

    assert result.status == ReconciliationStatus.CLEAN
    assert result.discrepancies == ()
    assert result.manual_recovery_required is False
    assert result.expected_position == observed_position


def test_reconcile_detects_fill_without_intent() -> None:
    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(),
        fills=(_fill(),),
        observed_position=new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        reconciled_at=NOW,
    )

    assert result.status == ReconciliationStatus.DIRTY
    assert result.manual_recovery_required is True
    assert _types(result) == (ReconciliationDiscrepancyType.FILL_WITHOUT_INTENT,)


def test_reconcile_detects_intent_without_fill() -> None:
    intent = _intent()

    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(intent,),
        fills=(),
        observed_position=new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        reconciled_at=NOW,
    )

    assert ReconciliationDiscrepancyType.INTENT_WITHOUT_FILL in _types(result)
    assert ReconciliationDiscrepancyType.INTENT_FILL_QUANTITY_MISMATCH in _types(result)


def test_reconcile_detects_fill_quantity_mismatch() -> None:
    intent = _intent(filled_quantity=Decimal("1"))
    fill = _fill(quantity=Decimal("0.4"), notional=Decimal("40"))

    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(intent,),
        fills=(fill,),
        observed_position=new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        reconciled_at=NOW,
    )

    assert ReconciliationDiscrepancyType.INTENT_FILL_QUANTITY_MISMATCH in _types(result)


def test_reconcile_detects_position_quantity_mismatch() -> None:
    intent = _intent()
    fill = _fill()
    observed_position = apply_fill_to_position(
        new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        intent,
        fill,
        updated_at=NOW,
    )

    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(intent,),
        fills=(fill,),
        observed_position=replace(observed_position, spot_quantity=Decimal("0.5")),
        reconciled_at=NOW,
    )

    assert ReconciliationDiscrepancyType.POSITION_QUANTITY_MISMATCH in _types(result)


def test_reconcile_detects_symbol_mismatch() -> None:
    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(_intent(symbol="ETHUSDT"),),
        fills=(_fill(symbol="ETHUSDT"),),
        observed_position=new_empty_position(symbol="ETHUSDT", opened_at=NOW),
        reconciled_at=NOW,
    )

    assert _types(result).count(ReconciliationDiscrepancyType.SYMBOL_MISMATCH) == 3


def test_reconcile_detects_position_rebuild_failure() -> None:
    intent = _intent(
        intent_id="intent_spot_close",
        leg=OrderIntentLeg.SPOT_CLOSE,
        side=OrderSide.SELL,
    )

    result = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=(intent,),
        fills=(_fill(intent_id="intent_spot_close", side=OrderSide.SELL),),
        observed_position=new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        reconciled_at=NOW,
    )

    assert ReconciliationDiscrepancyType.POSITION_REBUILD_FAILED in _types(result)
    assert result.expected_position is None


def _types(result) -> tuple[ReconciliationDiscrepancyType, ...]:
    return tuple(discrepancy.type for discrepancy in result.discrepancies)
