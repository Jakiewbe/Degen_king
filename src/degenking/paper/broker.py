"""Deterministic in-memory paper broker.

The paper broker consumes risk-approved OrderIntents and simulates fills. It is
not an exchange client and contains no network or live-order placement code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from degenking.market_data.models import OrderBookSnapshot
from degenking.orders.idempotency import IdempotencyLedger
from degenking.orders.intents import OrderIntent, OrderIntentState
from degenking.orders.state_machine import transition_intent
from degenking.paper.fill_model import (
    PaperFillResult,
    PaperFillStatus,
    simulate_limit_fill,
)


@dataclass(frozen=True, slots=True)
class PaperBrokerResult:
    """Result of submitting one risk-approved intent to the paper broker."""

    accepted: bool
    intent: OrderIntent
    fill: PaperFillResult | None = None
    reason: str | None = None


@dataclass(slots=True)
class PaperBroker:
    """Small deterministic broker facade for paper execution tests."""

    idempotency: IdempotencyLedger = field(default_factory=IdempotencyLedger)
    intents_by_id: dict[str, OrderIntent] = field(default_factory=dict)
    fills_by_intent_id: dict[str, PaperFillResult] = field(default_factory=dict)

    def submit(
        self,
        intent: OrderIntent,
        orderbook: OrderBookSnapshot,
        *,
        submitted_at: datetime,
        taker_fee_bps: Decimal,
        fill_ratio: Decimal = Decimal("1"),
        reference_price: Decimal | None = None,
    ) -> PaperBrokerResult:
        """Submit a risk-approved paper intent and simulate its immediate fill."""

        if intent.state != OrderIntentState.RISK_APPROVED:
            raise ValueError("paper broker only accepts risk-approved intents")

        if not self.idempotency.register(intent.idempotency_key):
            suppressed = transition_intent(
                intent,
                OrderIntentState.DUPLICATE_SUPPRESSED,
                updated_at=submitted_at,
            )
            self.intents_by_id[suppressed.intent_id] = suppressed
            return PaperBrokerResult(
                accepted=False,
                intent=suppressed,
                reason="duplicate_intent_suppressed",
            )

        submitted = transition_intent(
            intent,
            OrderIntentState.SUBMITTED_TO_PAPER_BROKER,
            updated_at=submitted_at,
            exchange_order_id=_paper_order_id(intent),
        )
        acknowledged = transition_intent(
            submitted,
            OrderIntentState.ACKNOWLEDGED,
            updated_at=submitted_at,
        )
        fill = simulate_limit_fill(
            acknowledged,
            orderbook,
            taker_fee_bps=taker_fee_bps,
            fill_ratio=fill_ratio,
            reference_price=reference_price,
        )
        final_intent = _apply_fill_state(acknowledged, fill, updated_at=submitted_at)

        self.intents_by_id[final_intent.intent_id] = final_intent
        if fill.status != PaperFillStatus.NO_FILL:
            self.fills_by_intent_id[final_intent.intent_id] = fill

        return PaperBrokerResult(accepted=True, intent=final_intent, fill=fill)


def _apply_fill_state(
    intent: OrderIntent,
    fill: PaperFillResult,
    *,
    updated_at: datetime,
) -> OrderIntent:
    if fill.status == PaperFillStatus.NO_FILL:
        return intent
    if fill.status == PaperFillStatus.PARTIAL_FILL:
        return transition_intent(
            intent,
            OrderIntentState.PARTIALLY_FILLED,
            updated_at=updated_at,
            filled_quantity=fill.filled_quantity,
        )
    return transition_intent(
        intent,
        OrderIntentState.FILLED,
        updated_at=updated_at,
        filled_quantity=fill.filled_quantity,
    )


def _paper_order_id(intent: OrderIntent) -> str:
    return f"paper_{intent.client_order_id}"
