"""Audit event contracts and deterministic event builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from degenking.common.enums import EventSeverity
from degenking.common.ids import new_trace_id
from degenking.common.time import utc_now
from degenking.orders.intents import OrderIntent
from degenking.paper.fill_model import PaperFillResult
from degenking.positions.manager import HedgedPosition
from degenking.positions.pnl import PositionPnL
from degenking.reconciliation.service import ReconciliationResult
from degenking.reconciliation.startup_recovery import StartupRecoveryDecision
from degenking.risk.engine import RiskEngineDecision
from degenking.risk.execution_guards import ExecutionGuardDecision
from degenking.risk.kill_switch import KillSwitchDecision
from degenking.risk.pre_trade import PreTradeRiskDecision
from degenking.strategy.opportunity import OpportunityEvaluation


class AuditEventType(StrEnum):
    """Canonical audit event names for MVP paper trading."""

    OPPORTUNITY_EVALUATED = "opportunity_evaluated"
    PRE_TRADE_RISK_DECIDED = "pre_trade_risk_decided"
    RISK_ENGINE_DECIDED = "risk_engine_decided"
    EXECUTION_GUARD_DECIDED = "execution_guard_decided"
    KILL_SWITCH_DECIDED = "kill_switch_decided"
    ORDER_INTENT_UPDATED = "order_intent_updated"
    PAPER_FILL_RECORDED = "paper_fill_recorded"
    POSITION_UPDATED = "position_updated"
    PNL_RECORDED = "pnl_recorded"
    RECONCILIATION_COMPLETED = "reconciliation_completed"
    STARTUP_RECOVERY_DECIDED = "startup_recovery_decided"


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Trace metadata copied onto related audit events."""

    trace_id: str
    run_id: str | None = None
    strategy_id: str | None = None
    config_hash: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Append-only event used for traceable system decisions."""

    event_type: str
    component: str
    payload: dict[str, Any]
    trace_id: str = field(default_factory=new_trace_id)
    run_id: str | None = None
    strategy_id: str | None = None
    config_hash: str | None = None
    severity: EventSeverity = EventSeverity.INFO
    created_at: datetime = field(default_factory=utc_now)


def opportunity_event(
    evaluation: OpportunityEvaluation,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for one opportunity evaluation."""

    return _event(
        event_type=AuditEventType.OPPORTUNITY_EVALUATED,
        component="strategy",
        context=context,
        payload={
            "symbol": evaluation.symbol,
            "should_enter": evaluation.signal.should_enter,
            "risk_approved": evaluation.risk_decision.approved,
            "net_edge_quote": evaluation.signal.edge.net_edge_quote,
            "net_edge_bps": evaluation.signal.edge.net_edge_bps,
            "funding_rate_bps": evaluation.signal.edge.funding_rate_bps,
            "signal_reasons": evaluation.signal.reasons,
            "risk_rejection_reasons": evaluation.risk_decision.rejection_reasons,
        },
    )


def pre_trade_risk_event(
    decision: PreTradeRiskDecision,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for Layer A pre-trade risk."""

    return _event(
        event_type=AuditEventType.PRE_TRADE_RISK_DECIDED,
        component="risk",
        context=context,
        severity=EventSeverity.INFO if decision.approved else EventSeverity.WARNING,
        payload={
            "approved": decision.approved,
            "checks": tuple(
                {
                    "name": check.name.value,
                    "passed": check.passed,
                    "observed_value": check.observed_value,
                    "limit_value": check.limit_value,
                    "reason": check.reason,
                }
                for check in decision.checks
            ),
            "rejection_reasons": decision.rejection_reasons,
        },
    )


def risk_engine_event(
    decision: RiskEngineDecision,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for the unified risk engine decision."""

    severity = (
        EventSeverity.CRITICAL
        if decision.manual_recovery_required or decision.block_global
        else EventSeverity.WARNING
        if not decision.allow_new_entry
        else EventSeverity.INFO
    )
    return _event(
        event_type=AuditEventType.RISK_ENGINE_DECIDED,
        component="risk",
        context=context,
        severity=severity,
        payload={
            "allow_new_entry": decision.allow_new_entry,
            "block_symbol": decision.block_symbol,
            "block_global": decision.block_global,
            "manual_recovery_required": decision.manual_recovery_required,
            "reasons": tuple(reason.value for reason in decision.reasons),
            "source_reasons": decision.source_reasons,
            "pre_trade_approved": decision.pre_trade_approved,
            "execution_passed": decision.execution_passed,
            "kill_switch_active": decision.kill_switch_active,
            "startup_new_entries_allowed": decision.startup_new_entries_allowed,
        },
    )


def execution_guard_event(
    decision: ExecutionGuardDecision,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for Layer B execution guards."""

    return _event(
        event_type=AuditEventType.EXECUTION_GUARD_DECIDED,
        component="risk",
        context=context,
        severity=EventSeverity.INFO if decision.passed else EventSeverity.ERROR,
        payload={
            "passed": decision.passed,
            "reasons": tuple(reason.value for reason in decision.reasons),
            "block_new_entries": decision.block_new_entries,
            "manual_recovery_required": decision.manual_recovery_required,
        },
    )


def kill_switch_event(
    decision: KillSwitchDecision,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for Layer D kill-switch evaluation."""

    return _event(
        event_type=AuditEventType.KILL_SWITCH_DECIDED,
        component="risk",
        context=context,
        severity=EventSeverity.CRITICAL if decision.active else EventSeverity.INFO,
        payload={
            "active": decision.active,
            "mode": decision.mode.value,
            "triggers": tuple(trigger.value for trigger in decision.triggers),
            "block_new_entries": decision.block_new_entries,
            "simulate_cancel_close": decision.simulate_cancel_close,
            "enforce_cancel_close": decision.enforce_cancel_close,
            "manual_reset_required": decision.manual_reset_required,
            "reason": decision.reason,
        },
    )


def order_intent_event(
    intent: OrderIntent,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for an OrderIntent state update."""

    return _event(
        event_type=AuditEventType.ORDER_INTENT_UPDATED,
        component="orders",
        context=context,
        payload={
            "intent_id": intent.intent_id,
            "idempotency_key": intent.idempotency_key,
            "symbol": intent.symbol,
            "leg": intent.leg.value,
            "side": intent.side.value,
            "state": intent.state.value,
            "quantity": intent.quantity,
            "filled_quantity": intent.filled_quantity,
            "residual_quantity": intent.residual_quantity,
            "notional_quote": intent.notional_quote,
            "limit_price": intent.limit_price,
            "client_order_id": intent.client_order_id,
            "exchange_order_id": intent.exchange_order_id,
        },
    )


def paper_fill_event(
    fill: PaperFillResult,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for a simulated paper fill."""

    return _event(
        event_type=AuditEventType.PAPER_FILL_RECORDED,
        component="paper",
        context=context,
        payload={
            "intent_id": fill.intent_id,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "status": fill.status.value,
            "filled_quantity": fill.filled_quantity,
            "remaining_quantity": fill.remaining_quantity,
            "filled_notional_quote": fill.filled_notional_quote,
            "average_price": fill.average_price,
            "fee_quote": fill.fee_quote,
            "slippage_quote": fill.slippage_quote,
            "slippage_bps": fill.slippage_bps,
            "levels_consumed": fill.levels_consumed,
            "fully_filled": fill.fully_filled,
        },
    )


def position_event(
    position: HedgedPosition,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for a paper position update."""

    return _event(
        event_type=AuditEventType.POSITION_UPDATED,
        component="positions",
        context=context,
        payload={
            "symbol": position.symbol,
            "spot_quantity": position.spot_quantity,
            "perp_quantity": position.perp_quantity,
            "delta_quantity": position.delta_quantity,
            "spot_entry_notional_quote": position.spot_entry_notional_quote,
            "perp_entry_notional_quote": position.perp_entry_notional_quote,
            "fees_quote": position.fees_quote,
            "slippage_quote": position.slippage_quote,
            "funding_pnl_quote": position.funding_pnl_quote,
            "state": position.state.value,
        },
    )


def pnl_event(
    pnl: PositionPnL,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for paper PnL attribution."""

    return _event(
        event_type=AuditEventType.PNL_RECORDED,
        component="positions",
        context=context,
        payload={
            "symbol": pnl.symbol,
            "spot_market_value_quote": pnl.spot_market_value_quote,
            "perp_mark_value_quote": pnl.perp_mark_value_quote,
            "spot_unrealized_pnl_quote": pnl.spot_unrealized_pnl_quote,
            "perp_unrealized_pnl_quote": pnl.perp_unrealized_pnl_quote,
            "funding_pnl_quote": pnl.funding_pnl_quote,
            "fees_quote": pnl.fees_quote,
            "slippage_quote": pnl.slippage_quote,
            "total_pnl_quote": pnl.total_pnl_quote,
            "delta_quantity": pnl.delta_quantity,
            "delta_notional_quote": pnl.delta_notional_quote,
        },
    )


def reconciliation_event(
    result: ReconciliationResult,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for reconciliation results."""

    return _event(
        event_type=AuditEventType.RECONCILIATION_COMPLETED,
        component="reconciliation",
        context=context,
        severity=EventSeverity.INFO
        if not result.manual_recovery_required
        else EventSeverity.ERROR,
        payload={
            "symbol": result.symbol,
            "status": result.status.value,
            "discrepancy_count": len(result.discrepancies),
            "discrepancies": tuple(
                {
                    "type": discrepancy.type.value,
                    "entity_id": discrepancy.entity_id,
                    "expected": discrepancy.expected,
                    "observed": discrepancy.observed,
                    "reason": discrepancy.reason,
                }
                for discrepancy in result.discrepancies
            ),
            "manual_recovery_required": result.manual_recovery_required,
        },
    )


def startup_recovery_event(
    decision: StartupRecoveryDecision,
    *,
    context: AuditContext,
) -> AuditEvent:
    """Build an audit event for startup recovery gating."""

    return _event(
        event_type=AuditEventType.STARTUP_RECOVERY_DECIDED,
        component="reconciliation",
        context=context,
        severity=EventSeverity.INFO
        if decision.new_entries_allowed
        else EventSeverity.CRITICAL
        if decision.manual_recovery_required
        else EventSeverity.WARNING,
        payload={
            "action": decision.action.value,
            "new_entries_allowed": decision.new_entries_allowed,
            "manual_recovery_required": decision.manual_recovery_required,
            "issues": tuple(
                {
                    "type": issue.type.value,
                    "entity_id": issue.entity_id,
                    "reason": issue.reason,
                }
                for issue in decision.issues
            ),
        },
    )


def _event(
    *,
    event_type: AuditEventType,
    component: str,
    context: AuditContext,
    payload: dict[str, Any],
    severity: EventSeverity = EventSeverity.INFO,
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type.value,
        component=component,
        payload=_normalize_payload(payload),
        trace_id=context.trace_id,
        run_id=context.run_id,
        strategy_id=context.strategy_id,
        config_hash=context.config_hash,
        severity=severity,
        created_at=context.created_at or utc_now(),
    )


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_payload(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return tuple(_normalize_payload(item) for item in value)
    if isinstance(value, Decimal):
        return str(value)
    return value
