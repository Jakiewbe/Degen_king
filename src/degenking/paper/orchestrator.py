"""Deterministic paper-entry orchestration.

This module composes existing pure/deterministic services for one paper entry
attempt. It does not access exchanges and does not place live orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from degenking.audit.events import (
    AuditContext,
    AuditEvent,
    order_intent_event,
    paper_fill_event,
    pnl_event,
    position_event,
    pre_trade_risk_event,
    reconciliation_event,
    risk_engine_event,
)
from degenking.common.enums import RuntimeMode
from degenking.orders.idempotency import build_client_order_id, build_idempotency_key
from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.broker import PaperBroker
from degenking.paper.fill_model import PaperFillResult
from degenking.positions.manager import (
    HedgedPosition,
    apply_fill_to_position,
    new_empty_position,
)
from degenking.positions.pnl import PositionPnL, calculate_position_pnl
from degenking.reconciliation.service import ReconciliationResult, reconcile_paper_state
from degenking.risk.engine import RiskEngineDecision, aggregate_risk_decisions
from degenking.strategy.opportunity import (
    OpportunityEvaluation,
    OpportunityEvaluationInputs,
    evaluate_funding_opportunity,
)


@dataclass(frozen=True, slots=True)
class PaperEntryRunInputs:
    """Inputs for one paper spot-long/perp-short entry attempt."""

    opportunity_inputs: OpportunityEvaluationInputs
    trace_id: str
    run_id: str
    strategy_id: str
    config_hash: str
    submitted_at: datetime
    spot_taker_fee_bps: Decimal
    perp_taker_fee_bps: Decimal
    fill_ratio: Decimal = Decimal("1")
    initial_position: HedgedPosition | None = None


@dataclass(frozen=True, slots=True)
class PaperEntryRunResult:
    """Result of one paper entry attempt."""

    opportunity: OpportunityEvaluation
    risk_decision: RiskEngineDecision
    intents: tuple[OrderIntent, ...]
    fills: tuple[PaperFillResult, ...]
    position: HedgedPosition
    pnl: PositionPnL | None
    reconciliation: ReconciliationResult | None
    audit_events: tuple[AuditEvent, ...]


def execute_paper_entry_run(inputs: PaperEntryRunInputs) -> PaperEntryRunResult:
    """Evaluate and, if approved, simulate one paper funding-arb entry."""

    context = AuditContext(
        trace_id=inputs.trace_id,
        run_id=inputs.run_id,
        strategy_id=inputs.strategy_id,
        config_hash=inputs.config_hash,
        created_at=inputs.submitted_at,
    )
    opportunity = evaluate_funding_opportunity(inputs.opportunity_inputs)
    risk_decision = aggregate_risk_decisions(pre_trade=opportunity.risk_decision)
    audit_events: list[AuditEvent] = [
        pre_trade_risk_event(opportunity.risk_decision, context=context),
        risk_engine_event(risk_decision, context=context),
    ]
    position = inputs.initial_position or new_empty_position(
        symbol=opportunity.symbol,
        opened_at=inputs.submitted_at,
    )

    if not risk_decision.allow_new_entry:
        return PaperEntryRunResult(
            opportunity=opportunity,
            risk_decision=risk_decision,
            intents=(),
            fills=(),
            position=position,
            pnl=None,
            reconciliation=None,
            audit_events=tuple(audit_events),
        )

    spot_intent = _build_intent(
        trace_id=inputs.trace_id,
        run_id=inputs.run_id,
        strategy_id=inputs.strategy_id,
        config_hash=inputs.config_hash,
        logical_action_id=f"{inputs.trace_id}:spot_open",
        symbol=opportunity.symbol,
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        quantity=opportunity.spot_precision.rounded_quantity,
        notional_quote=opportunity.spot_precision.notional_quote,
        limit_price=opportunity.spot_precision.rounded_price,
        created_at=inputs.submitted_at,
    )
    perp_intent = _build_intent(
        trace_id=inputs.trace_id,
        run_id=inputs.run_id,
        strategy_id=inputs.strategy_id,
        config_hash=inputs.config_hash,
        logical_action_id=f"{inputs.trace_id}:perp_open",
        symbol=opportunity.symbol,
        leg=OrderIntentLeg.PERP_OPEN,
        side=OrderSide.SELL,
        quantity=opportunity.perp_precision.rounded_quantity,
        notional_quote=opportunity.perp_precision.notional_quote,
        limit_price=opportunity.perp_precision.rounded_price,
        created_at=inputs.submitted_at,
    )

    broker = PaperBroker()
    spot_result = broker.submit(
        spot_intent,
        inputs.opportunity_inputs.spot_orderbook,
        submitted_at=inputs.submitted_at,
        taker_fee_bps=inputs.spot_taker_fee_bps,
        fill_ratio=inputs.fill_ratio,
    )
    perp_result = broker.submit(
        perp_intent,
        inputs.opportunity_inputs.perp_orderbook,
        submitted_at=inputs.submitted_at,
        taker_fee_bps=inputs.perp_taker_fee_bps,
        fill_ratio=inputs.fill_ratio,
    )
    intents = (spot_result.intent, perp_result.intent)
    fills = tuple(
        fill for fill in (spot_result.fill, perp_result.fill) if fill is not None
    )

    for intent, fill in zip(intents, fills, strict=True):
        position = apply_fill_to_position(
            position,
            intent,
            fill,
            updated_at=inputs.submitted_at,
        )

    pnl = calculate_position_pnl(
        position,
        spot_mid=inputs.opportunity_inputs.spot_ticker.mid,
        perp_mark=inputs.opportunity_inputs.perp_ticker.mark_or_mid,
    )
    reconciliation = reconcile_paper_state(
        symbol=opportunity.symbol,
        intents=intents,
        fills=fills,
        observed_position=position,
        reconciled_at=inputs.submitted_at,
    )

    audit_events.extend(order_intent_event(intent, context=context) for intent in intents)
    audit_events.extend(paper_fill_event(fill, context=context) for fill in fills)
    audit_events.extend(
        (
            position_event(position, context=context),
            pnl_event(pnl, context=context),
            reconciliation_event(reconciliation, context=context),
        )
    )
    return PaperEntryRunResult(
        opportunity=opportunity,
        risk_decision=risk_decision,
        intents=intents,
        fills=fills,
        position=position,
        pnl=pnl,
        reconciliation=reconciliation,
        audit_events=tuple(audit_events),
    )


def _build_intent(
    *,
    trace_id: str,
    run_id: str,
    strategy_id: str,
    config_hash: str,
    logical_action_id: str,
    symbol: str,
    leg: OrderIntentLeg,
    side: OrderSide,
    quantity: Decimal,
    notional_quote: Decimal,
    limit_price: Decimal,
    created_at: datetime,
) -> OrderIntent:
    idempotency_key = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id=strategy_id,
        symbol=symbol,
        leg=leg,
        side=side,
        logical_action_id=logical_action_id,
    )
    return OrderIntent(
        intent_id=logical_action_id,
        trace_id=trace_id,
        run_id=run_id,
        strategy_id=strategy_id,
        config_hash=config_hash,
        idempotency_key=idempotency_key,
        symbol=symbol,
        leg=leg,
        side=side,
        quantity=quantity,
        notional_quote=notional_quote,
        limit_price=limit_price,
        client_order_id=build_client_order_id(
            mode=RuntimeMode.PAPER,
            strategy_id=strategy_id,
            symbol=symbol,
            leg=leg,
            idempotency_key=idempotency_key,
        ),
        created_at=created_at,
        updated_at=created_at,
        state=OrderIntentState.RISK_APPROVED,
    )
