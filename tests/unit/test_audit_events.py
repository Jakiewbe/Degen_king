from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from degenking.audit.events import (
    AuditContext,
    AuditEventType,
    execution_guard_event,
    kill_switch_event,
    order_intent_event,
    paper_fill_event,
    pnl_event,
    position_event,
    pre_trade_risk_event,
    reconciliation_event,
    risk_engine_event,
    startup_recovery_event,
)
from degenking.common.enums import EventSeverity, KillSwitchMode
from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.fill_model import PaperFillResult, PaperFillStatus
from degenking.positions.manager import HedgedPosition, PositionState
from degenking.positions.pnl import PositionPnL
from degenking.reconciliation.service import (
    ReconciliationDiscrepancy,
    ReconciliationDiscrepancyType,
    ReconciliationResult,
    ReconciliationStatus,
)
from degenking.reconciliation.startup_recovery import (
    StartupRecoveryAction,
    StartupRecoveryDecision,
    StartupRecoveryIssue,
    StartupRecoveryIssueType,
)
from degenking.risk.engine import RiskEngineDecision, RiskEngineReason
from degenking.risk.execution_guards import (
    ExecutionGuardDecision,
    ExecutionGuardReason,
)
from degenking.risk.kill_switch import KillSwitchDecision, KillSwitchTrigger
from degenking.risk.pre_trade import PreTradeRiskDecision, RiskCheck, RiskCheckName

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
CONTEXT = AuditContext(
    trace_id="trace_1",
    run_id="run_1",
    strategy_id="funding_v1",
    config_hash="config_hash",
    created_at=NOW,
)


def test_pre_trade_risk_event_captures_failed_checks() -> None:
    decision = PreTradeRiskDecision(
        approved=False,
        checks=(
            RiskCheck(
                name=RiskCheckName.SLIPPAGE,
                passed=False,
                observed_value="12",
                limit_value="10",
                reason="slippage_or_fill_depth_exceeds_limit",
            ),
        ),
    )

    event = pre_trade_risk_event(decision, context=CONTEXT)

    assert event.event_type == AuditEventType.PRE_TRADE_RISK_DECIDED.value
    assert event.component == "risk"
    assert event.severity == EventSeverity.WARNING
    assert event.trace_id == "trace_1"
    assert event.payload["approved"] is False
    assert event.payload["rejection_reasons"] == (
        "slippage_or_fill_depth_exceeds_limit",
    )


def test_risk_engine_event_uses_critical_severity_for_global_block() -> None:
    event = risk_engine_event(
        RiskEngineDecision(
            allow_new_entry=False,
            block_symbol=False,
            block_global=True,
            manual_recovery_required=True,
            reasons=(RiskEngineReason.KILL_SWITCH_ACTIVE,),
            source_reasons=("daily_loss_limit",),
        ),
        context=CONTEXT,
    )

    assert event.severity == EventSeverity.CRITICAL
    assert event.payload["block_global"] is True
    assert event.payload["manual_recovery_required"] is True
    assert event.payload["reasons"] == ("kill_switch_active",)


def test_execution_guard_event_records_reasons() -> None:
    event = execution_guard_event(
        ExecutionGuardDecision(
            passed=False,
            reasons=(ExecutionGuardReason.RESIDUAL_EXPOSURE,),
            block_new_entries=True,
            manual_recovery_required=True,
        ),
        context=CONTEXT,
    )

    assert event.event_type == AuditEventType.EXECUTION_GUARD_DECIDED.value
    assert event.severity == EventSeverity.ERROR
    assert event.payload["reasons"] == ("residual_exposure",)


def test_kill_switch_event_records_mode_and_triggers() -> None:
    event = kill_switch_event(
        KillSwitchDecision(
            active=True,
            mode=KillSwitchMode.SIMULATED,
            triggers=(KillSwitchTrigger.DAILY_LOSS_LIMIT,),
            block_new_entries=True,
            simulate_cancel_close=True,
            enforce_cancel_close=False,
            manual_reset_required=True,
            reason="daily_loss_limit",
        ),
        context=CONTEXT,
    )

    assert event.event_type == AuditEventType.KILL_SWITCH_DECIDED.value
    assert event.severity == EventSeverity.CRITICAL
    assert event.payload["mode"] == "simulated"
    assert event.payload["triggers"] == ("daily_loss_limit",)


def test_order_intent_event_records_idempotency_and_state() -> None:
    event = order_intent_event(_intent(), context=CONTEXT)

    assert event.component == "orders"
    assert event.payload["intent_id"] == "intent_1"
    assert event.payload["idempotency_key"] == "idem_1"
    assert event.payload["state"] == "filled"
    assert event.payload["quantity"] == "1"
    assert event.payload["residual_quantity"] == "0"


def test_paper_fill_event_records_fee_and_slippage() -> None:
    event = paper_fill_event(_fill(), context=CONTEXT)

    assert event.component == "paper"
    assert event.payload["status"] == "full_fill"
    assert event.payload["fee_quote"] == "0.1"
    assert event.payload["slippage_bps"] == "2"


def test_position_and_pnl_events_stringify_decimal_payloads() -> None:
    position = HedgedPosition(
        symbol="BTCUSDT",
        spot_quantity=Decimal("1"),
        perp_quantity=Decimal("-1"),
        spot_entry_notional_quote=Decimal("100"),
        perp_entry_notional_quote=Decimal("100"),
        fees_quote=Decimal("0.2"),
        slippage_quote=Decimal("0.4"),
        funding_pnl_quote=Decimal("1.5"),
        opened_at=NOW,
        updated_at=NOW,
    )
    pnl = PositionPnL(
        symbol="BTCUSDT",
        spot_market_value_quote=Decimal("101"),
        perp_mark_value_quote=Decimal("100"),
        spot_unrealized_pnl_quote=Decimal("1"),
        perp_unrealized_pnl_quote=Decimal("0"),
        funding_pnl_quote=Decimal("1.5"),
        fees_quote=Decimal("0.2"),
        slippage_quote=Decimal("0.4"),
        total_pnl_quote=Decimal("1.9"),
        delta_quantity=Decimal("0"),
        delta_notional_quote=Decimal("0"),
    )

    position_audit = position_event(position, context=CONTEXT)
    pnl_audit = pnl_event(pnl, context=CONTEXT)

    assert position_audit.payload["delta_quantity"] == "0"
    assert position_audit.payload["state"] == "open"
    assert pnl_audit.payload["total_pnl_quote"] == "1.9"
    assert pnl_audit.payload["delta_notional_quote"] == "0"


def test_reconciliation_event_records_discrepancies() -> None:
    position = HedgedPosition(
        symbol="BTCUSDT",
        spot_quantity=Decimal("0"),
        perp_quantity=Decimal("0"),
        spot_entry_notional_quote=Decimal("0"),
        perp_entry_notional_quote=Decimal("0"),
        fees_quote=Decimal("0"),
        slippage_quote=Decimal("0"),
        funding_pnl_quote=Decimal("0"),
        opened_at=NOW,
        updated_at=NOW,
        state=PositionState.CLOSED,
    )
    result = ReconciliationResult(
        symbol="BTCUSDT",
        status=ReconciliationStatus.DIRTY,
        discrepancies=(
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.FILL_WITHOUT_INTENT,
                entity_id="fill_1",
                expected="matching_intent",
                observed="missing",
                reason="fill_has_no_matching_intent",
            ),
        ),
        expected_position=None,
        observed_position=position,
        reconciled_at=NOW,
        manual_recovery_required=True,
    )

    event = reconciliation_event(result, context=CONTEXT)

    assert event.severity == EventSeverity.ERROR
    assert event.payload["status"] == "dirty"
    assert event.payload["discrepancy_count"] == 1
    assert event.payload["discrepancies"][0]["type"] == "fill_without_intent"


def test_startup_recovery_event_records_issues() -> None:
    event = startup_recovery_event(
        StartupRecoveryDecision(
            action=StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY,
            issues=(
                StartupRecoveryIssue(
                    type=StartupRecoveryIssueType.DIRTY_RECONCILIATION,
                    entity_id="BTCUSDT",
                    reason="dirty_reconciliation_result_loaded_at_startup",
                ),
            ),
            evaluated_at=NOW,
        ),
        context=CONTEXT,
    )

    assert event.severity == EventSeverity.CRITICAL
    assert event.payload["manual_recovery_required"] is True
    assert event.payload["issues"][0]["type"] == "dirty_reconciliation"


def test_audit_event_builders_preserve_context_metadata() -> None:
    event = order_intent_event(_intent(), context=CONTEXT)

    assert event.trace_id == "trace_1"
    assert event.run_id == "run_1"
    assert event.strategy_id == "funding_v1"
    assert event.config_hash == "config_hash"
    assert event.created_at == NOW


def _intent() -> OrderIntent:
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
        state=OrderIntentState.FILLED,
        filled_quantity=Decimal("1"),
    )


def _fill() -> PaperFillResult:
    return PaperFillResult(
        intent_id="intent_1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        status=PaperFillStatus.FULL_FILL,
        filled_quantity=Decimal("1"),
        remaining_quantity=Decimal("0"),
        filled_notional_quote=Decimal("100"),
        average_price=Decimal("100"),
        fee_quote=Decimal("0.1"),
        slippage_quote=Decimal("0.2"),
        slippage_bps=Decimal("2"),
        levels_consumed=1,
        fully_filled=True,
    )
