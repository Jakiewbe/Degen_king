"""Pure domain-to-persistence mappers.

Converts domain decision/event objects into persistence model records.
No database connection. No ORM. No broker calls. Deterministic only.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from degenking.audit.events import AuditEvent
from degenking.orders.intents import OrderIntent
from degenking.paper.fill_model import PaperFillResult
from degenking.persistence.models import (
    FillRecord,
    OrderIntentRecord,
    PnlRecord,
    PositionRecord,
    ReconciliationRunRecord,
    RiskCheckRecord,
    RiskIncidentRecord,
    SystemEventRecord,
)
from degenking.positions.manager import HedgedPosition, PositionState
from degenking.positions.pnl import PositionPnL
from degenking.reconciliation.service import ReconciliationResult
from degenking.risk.kill_switch import KillSwitchDecision
from degenking.risk.pre_trade import RiskCheck


def order_intent_to_record(
    intent: OrderIntent,
    record_id: str,
    *,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> OrderIntentRecord:
    """Map an OrderIntent domain object to an OrderIntentRecord."""
    return OrderIntentRecord(
        id=record_id,
        trace_id=intent.trace_id,
        run_id=intent.run_id,
        strategy_id=intent.strategy_id,
        config_hash=intent.config_hash,
        created_at=created_at if created_at is not None else intent.created_at,
        updated_at=updated_at if updated_at is not None else intent.updated_at,
        idempotency_key=intent.idempotency_key,
        client_order_id=intent.client_order_id,
        exchange_order_id=intent.exchange_order_id,
        leg=intent.leg.value,
        side=intent.side.value,
        symbol=intent.symbol,
        quantity=intent.quantity,
        limit_price=intent.limit_price,
        state=intent.state.value,
        filled_quantity=intent.filled_quantity,
    )


def fill_to_record(
    fill: PaperFillResult,
    record_id: str,
    *,
    order_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> FillRecord:
    """Map a PaperFillResult to a FillRecord."""
    return FillRecord(
        id=record_id,
        created_at=created_at,
        updated_at=updated_at,
        order_id=order_id,
        intent_id=fill.intent_id,
        symbol=fill.symbol,
        price=fill.average_price,
        quantity=fill.filled_quantity,
        fee=fill.fee_quote,
        liquidity="taker",
        filled_at=created_at,
    )


def position_to_record(
    position: HedgedPosition,
    record_id: str,
    *,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> PositionRecord:
    """Map a HedgedPosition to a PositionRecord."""
    effective_updated_at = updated_at if updated_at is not None else position.updated_at
    return PositionRecord(
        id=record_id,
        created_at=created_at if created_at is not None else position.opened_at,
        updated_at=effective_updated_at,
        symbol=position.symbol,
        spot_quantity=position.spot_quantity,
        perp_quantity=position.perp_quantity,
        delta_quantity=position.delta_quantity,
        spot_entry_notional=position.spot_entry_notional_quote,
        perp_entry_notional=position.perp_entry_notional_quote,
        fees_quote=position.fees_quote,
        slippage_quote=position.slippage_quote,
        funding_pnl_quote=position.funding_pnl_quote,
        state=position.state.value,
        opened_at=position.opened_at,
        closed_at=effective_updated_at if position.state == PositionState.CLOSED else None,
    )


def pnl_to_record(
    pnl: PositionPnL,
    record_id: str,
    *,
    position_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> PnlRecord:
    """Map a PositionPnL to a PnlRecord."""
    unrealized_pnl = pnl.spot_unrealized_pnl_quote + pnl.perp_unrealized_pnl_quote
    return PnlRecord(
        id=record_id,
        created_at=created_at,
        updated_at=updated_at,
        symbol=pnl.symbol,
        position_id=position_id,
        funding_pnl=pnl.funding_pnl_quote,
        trading_fees=pnl.fees_quote,
        slippage_cost=pnl.slippage_quote,
        realized_pnl=Decimal("0"),
        unrealized_pnl=unrealized_pnl,
        total_pnl=pnl.total_pnl_quote,
        calculated_at=created_at,
    )


def reconciliation_to_record(
    result: ReconciliationResult,
    record_id: str,
    *,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ReconciliationRunRecord:
    """Map a ReconciliationResult to a ReconciliationRunRecord."""
    discrepancy_count = len(result.discrepancies)
    discrepancies_text: str | None = None
    if discrepancy_count > 0:
        lines: list[str] = []
        for d in result.discrepancies:
            lines.append(
                f"{d.type.value}: {d.entity_id} "
                f"expected={d.expected} observed={d.observed} ({d.reason})"
            )
        discrepancies_text = "\n".join(lines)

    return ReconciliationRunRecord(
        id=record_id,
        created_at=created_at if created_at is not None else result.reconciled_at,
        updated_at=updated_at if updated_at is not None else result.reconciled_at,
        symbol=result.symbol,
        started_at=created_at if created_at is not None else result.reconciled_at,
        completed_at=created_at if created_at is not None else result.reconciled_at,
        status=result.status.value,
        discrepancy_count=discrepancy_count,
        discrepancies=discrepancies_text,
        manual_recovery_required=result.manual_recovery_required,
    )


def risk_check_to_record(
    check: RiskCheck,
    record_id: str,
    *,
    decision_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> RiskCheckRecord:
    """Map a RiskCheck to a RiskCheckRecord."""
    return RiskCheckRecord(
        id=record_id,
        created_at=created_at,
        updated_at=updated_at,
        decision_id=decision_id,
        check_name=check.name.value,
        passed=check.passed,
        observed_value=check.observed_value,
        limit_value=check.limit_value,
        reason=check.reason,
    )


def kill_switch_to_incident_record(
    decision: KillSwitchDecision,
    record_id: str,
    *,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> RiskIncidentRecord | None:
    """Map an active KillSwitchDecision to a RiskIncidentRecord.

    Returns None if the kill switch is not active.
    """
    if not decision.active:
        return None

    return RiskIncidentRecord(
        id=record_id,
        created_at=created_at,
        updated_at=updated_at,
        incident_type="kill_switch",
        severity="critical",
        trigger=";".join(t.value for t in decision.triggers),
        action_taken="block_new_entries",
        manual_reset_required=decision.manual_reset_required,
    )


def audit_event_to_system_event_record(
    event: AuditEvent,
    record_id: str,
    *,
    updated_at: datetime | None = None,
) -> SystemEventRecord:
    """Map an AuditEvent to a SystemEventRecord."""
    return SystemEventRecord(
        id=record_id,
        trace_id=event.trace_id,
        run_id=event.run_id,
        strategy_id=event.strategy_id,
        config_hash=event.config_hash,
        created_at=event.created_at,
        updated_at=updated_at if updated_at is not None else event.created_at,
        component=event.component,
        severity=event.severity.value,
        event_type=event.event_type,
        message=None,
        payload=str(event.payload),
    )
