"""Pure paper-state reconciliation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from degenking.orders.intents import OrderIntent, OrderIntentState
from degenking.paper.fill_model import PaperFillResult
from degenking.positions.manager import (
    HedgedPosition,
    apply_fill_to_position,
    new_empty_position,
)


class ReconciliationStatus(StrEnum):
    """Overall reconciliation outcome."""

    CLEAN = "clean"
    DIRTY = "dirty"


class ReconciliationDiscrepancyType(StrEnum):
    """Types of paper-state discrepancies."""

    FILL_WITHOUT_INTENT = "fill_without_intent"
    INTENT_WITHOUT_FILL = "intent_without_fill"
    INTENT_FILL_QUANTITY_MISMATCH = "intent_fill_quantity_mismatch"
    SYMBOL_MISMATCH = "symbol_mismatch"
    POSITION_QUANTITY_MISMATCH = "position_quantity_mismatch"
    POSITION_ENTRY_NOTIONAL_MISMATCH = "position_entry_notional_mismatch"
    POSITION_COST_MISMATCH = "position_cost_mismatch"
    POSITION_REBUILD_FAILED = "position_rebuild_failed"


@dataclass(frozen=True, slots=True)
class ReconciliationDiscrepancy:
    """One observed mismatch between expected and observed paper state."""

    type: ReconciliationDiscrepancyType
    entity_id: str
    expected: str
    observed: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Result of comparing intents, fills, and position state."""

    symbol: str
    status: ReconciliationStatus
    discrepancies: tuple[ReconciliationDiscrepancy, ...]
    expected_position: HedgedPosition | None
    observed_position: HedgedPosition
    reconciled_at: datetime
    manual_recovery_required: bool


def reconcile_paper_state(
    *,
    symbol: str,
    intents: tuple[OrderIntent, ...],
    fills: tuple[PaperFillResult, ...],
    observed_position: HedgedPosition,
    reconciled_at: datetime,
) -> ReconciliationResult:
    """Reconcile paper intents/fills against the observed position snapshot."""

    discrepancies: list[ReconciliationDiscrepancy] = []
    _check_symbols(symbol, intents, fills, observed_position, discrepancies)
    _check_intent_fill_linkage(intents, fills, discrepancies)
    expected_position = _rebuild_position(
        symbol=symbol,
        intents=intents,
        fills=fills,
        opened_at=observed_position.opened_at,
        updated_at=reconciled_at,
        discrepancies=discrepancies,
    )
    if expected_position is not None:
        _compare_positions(expected_position, observed_position, discrepancies)

    status = (
        ReconciliationStatus.CLEAN
        if not discrepancies
        else ReconciliationStatus.DIRTY
    )
    return ReconciliationResult(
        symbol=symbol,
        status=status,
        discrepancies=tuple(discrepancies),
        expected_position=expected_position,
        observed_position=observed_position,
        reconciled_at=reconciled_at,
        manual_recovery_required=bool(discrepancies),
    )


def _check_symbols(
    symbol: str,
    intents: tuple[OrderIntent, ...],
    fills: tuple[PaperFillResult, ...],
    observed_position: HedgedPosition,
    discrepancies: list[ReconciliationDiscrepancy],
) -> None:
    if observed_position.symbol != symbol:
        discrepancies.append(
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.SYMBOL_MISMATCH,
                entity_id="position",
                expected=symbol,
                observed=observed_position.symbol,
                reason="observed_position_symbol_mismatch",
            )
        )
    for intent in intents:
        if intent.symbol != symbol:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    type=ReconciliationDiscrepancyType.SYMBOL_MISMATCH,
                    entity_id=intent.intent_id,
                    expected=symbol,
                    observed=intent.symbol,
                    reason="intent_symbol_mismatch",
                )
            )
    for fill in fills:
        if fill.symbol != symbol:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    type=ReconciliationDiscrepancyType.SYMBOL_MISMATCH,
                    entity_id=fill.intent_id,
                    expected=symbol,
                    observed=fill.symbol,
                    reason="fill_symbol_mismatch",
                )
            )


def _check_intent_fill_linkage(
    intents: tuple[OrderIntent, ...],
    fills: tuple[PaperFillResult, ...],
    discrepancies: list[ReconciliationDiscrepancy],
) -> None:
    intents_by_id = {intent.intent_id: intent for intent in intents}
    fill_quantities_by_intent = _fill_quantities_by_intent(fills)

    for fill in fills:
        if fill.intent_id not in intents_by_id:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    type=ReconciliationDiscrepancyType.FILL_WITHOUT_INTENT,
                    entity_id=fill.intent_id,
                    expected="matching_intent",
                    observed="missing",
                    reason="fill_has_no_matching_intent",
                )
            )

    for intent in intents:
        fill_quantity = fill_quantities_by_intent.get(intent.intent_id, Decimal("0"))
        if _requires_fill(intent.state) and fill_quantity == 0:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    type=ReconciliationDiscrepancyType.INTENT_WITHOUT_FILL,
                    entity_id=intent.intent_id,
                    expected=str(intent.filled_quantity),
                    observed="0",
                    reason="filled_intent_has_no_fill",
                )
            )
        if intent.filled_quantity != fill_quantity:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    type=ReconciliationDiscrepancyType.INTENT_FILL_QUANTITY_MISMATCH,
                    entity_id=intent.intent_id,
                    expected=str(intent.filled_quantity),
                    observed=str(fill_quantity),
                    reason="intent_and_fill_quantities_differ",
                )
            )


def _rebuild_position(
    *,
    symbol: str,
    intents: tuple[OrderIntent, ...],
    fills: tuple[PaperFillResult, ...],
    opened_at: datetime,
    updated_at: datetime,
    discrepancies: list[ReconciliationDiscrepancy],
) -> HedgedPosition | None:
    intents_by_id = {intent.intent_id: intent for intent in intents}
    position = new_empty_position(symbol=symbol, opened_at=opened_at)
    try:
        for fill in fills:
            intent = intents_by_id.get(fill.intent_id)
            if intent is None:
                continue
            position = apply_fill_to_position(
                position,
                intent,
                fill,
                updated_at=updated_at,
            )
    except ValueError as exc:
        discrepancies.append(
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.POSITION_REBUILD_FAILED,
                entity_id=symbol,
                expected="rebuildable_position",
                observed="rebuild_failed",
                reason=str(exc),
            )
        )
        return None
    return position


def _compare_positions(
    expected: HedgedPosition,
    observed: HedgedPosition,
    discrepancies: list[ReconciliationDiscrepancy],
) -> None:
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_QUANTITY_MISMATCH,
        entity_id=expected.symbol,
        field="spot_quantity",
        expected=expected.spot_quantity,
        observed=observed.spot_quantity,
    )
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_QUANTITY_MISMATCH,
        entity_id=expected.symbol,
        field="perp_quantity",
        expected=expected.perp_quantity,
        observed=observed.perp_quantity,
    )
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_ENTRY_NOTIONAL_MISMATCH,
        entity_id=expected.symbol,
        field="spot_entry_notional_quote",
        expected=expected.spot_entry_notional_quote,
        observed=observed.spot_entry_notional_quote,
    )
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_ENTRY_NOTIONAL_MISMATCH,
        entity_id=expected.symbol,
        field="perp_entry_notional_quote",
        expected=expected.perp_entry_notional_quote,
        observed=observed.perp_entry_notional_quote,
    )
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_COST_MISMATCH,
        entity_id=expected.symbol,
        field="fees_quote",
        expected=expected.fees_quote,
        observed=observed.fees_quote,
    )
    _append_decimal_mismatch(
        discrepancies,
        mismatch_type=ReconciliationDiscrepancyType.POSITION_COST_MISMATCH,
        entity_id=expected.symbol,
        field="slippage_quote",
        expected=expected.slippage_quote,
        observed=observed.slippage_quote,
    )


def _append_decimal_mismatch(
    discrepancies: list[ReconciliationDiscrepancy],
    *,
    mismatch_type: ReconciliationDiscrepancyType,
    entity_id: str,
    field: str,
    expected: Decimal,
    observed: Decimal,
) -> None:
    if expected == observed:
        return
    discrepancies.append(
        ReconciliationDiscrepancy(
            type=mismatch_type,
            entity_id=entity_id,
            expected=str(expected),
            observed=str(observed),
            reason=f"{field}_mismatch",
        )
    )


def _fill_quantities_by_intent(
    fills: tuple[PaperFillResult, ...],
) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = {}
    for fill in fills:
        quantities[fill.intent_id] = (
            quantities.get(fill.intent_id, Decimal("0")) + fill.filled_quantity
        )
    return quantities


def _requires_fill(state: OrderIntentState) -> bool:
    return state in {
        OrderIntentState.PARTIALLY_FILLED,
        OrderIntentState.FILLED,
        OrderIntentState.RECONCILED,
        OrderIntentState.POSITION_UPDATED,
        OrderIntentState.CLOSED,
    }
