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
from degenking.positions.manager import new_empty_position
from degenking.reconciliation.service import (
    ReconciliationResult,
    ReconciliationStatus,
)
from degenking.reconciliation.startup_recovery import (
    StartupRecoveryAction,
    StartupRecoveryIssueType,
    evaluate_startup_recovery,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _intent(state: OrderIntentState = OrderIntentState.ACKNOWLEDGED) -> OrderIntent:
    return OrderIntent(
        intent_id="intent_1",
        trace_id="trace_1",
        run_id="run_1",
        strategy_id="funding_v1",
        config_hash="config_hash",
        idempotency_key="idem_1",
        symbol="BTCUSDT",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        notional_quote=Decimal("100"),
        limit_price=Decimal("100"),
        client_order_id="client_1",
        created_at=NOW,
        updated_at=NOW,
        state=state,
    )


def _clean_reconciliation() -> ReconciliationResult:
    position = new_empty_position(symbol="BTCUSDT", opened_at=NOW)
    return ReconciliationResult(
        symbol="BTCUSDT",
        status=ReconciliationStatus.CLEAN,
        discrepancies=(),
        expected_position=position,
        observed_position=position,
        reconciled_at=NOW,
        manual_recovery_required=False,
    )


def test_startup_recovery_allows_clean_flat_state() -> None:
    decision = evaluate_startup_recovery(
        open_intents=(),
        positions=(new_empty_position(symbol="BTCUSDT", opened_at=NOW),),
        reconciliation_results=(_clean_reconciliation(),),
        evaluated_at=NOW,
    )

    assert decision.action == StartupRecoveryAction.ALLOW_NEW_ENTRIES
    assert decision.new_entries_allowed is True
    assert decision.manual_recovery_required is False


def test_startup_recovery_blocks_non_terminal_intent() -> None:
    decision = evaluate_startup_recovery(
        open_intents=(_intent(),),
        positions=(),
        reconciliation_results=(),
        evaluated_at=NOW,
    )

    assert decision.action == StartupRecoveryAction.BLOCK_NEW_ENTRIES
    assert decision.new_entries_allowed is False
    assert _types(decision) == (StartupRecoveryIssueType.OPEN_INTENT,)


def test_startup_recovery_ignores_terminal_intent() -> None:
    decision = evaluate_startup_recovery(
        open_intents=(_intent(state=OrderIntentState.CLOSED),),
        positions=(),
        reconciliation_results=(),
        evaluated_at=NOW,
    )

    assert decision.action == StartupRecoveryAction.ALLOW_NEW_ENTRIES


def test_startup_recovery_blocks_open_position() -> None:
    open_position = replace(
        new_empty_position(symbol="BTCUSDT", opened_at=NOW),
        spot_quantity=Decimal("1"),
    )

    decision = evaluate_startup_recovery(
        open_intents=(),
        positions=(open_position,),
        reconciliation_results=(),
        evaluated_at=NOW,
    )

    assert decision.action == StartupRecoveryAction.BLOCK_NEW_ENTRIES
    assert _types(decision) == (StartupRecoveryIssueType.OPEN_POSITION,)


def test_startup_recovery_requires_manual_recovery_for_dirty_reconciliation() -> None:
    dirty = replace(
        _clean_reconciliation(),
        status=ReconciliationStatus.DIRTY,
        manual_recovery_required=True,
    )

    decision = evaluate_startup_recovery(
        open_intents=(),
        positions=(),
        reconciliation_results=(dirty,),
        evaluated_at=NOW,
    )

    assert decision.action == StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY
    assert decision.manual_recovery_required is True
    assert StartupRecoveryIssueType.DIRTY_RECONCILIATION in _types(decision)
    assert StartupRecoveryIssueType.MANUAL_RECOVERY_REQUIRED in _types(decision)


def _types(decision) -> tuple[StartupRecoveryIssueType, ...]:
    return tuple(issue.type for issue in decision.issues)
