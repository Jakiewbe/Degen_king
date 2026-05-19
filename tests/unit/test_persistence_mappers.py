"""Tests for domain-to-persistence mapper functions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from degenking.audit.events import AuditEvent
from degenking.common.enums import EventSeverity, KillSwitchMode
from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.fill_model import PaperFillResult, PaperFillStatus
from degenking.persistence.mappers import (
    audit_event_to_system_event_record,
    fill_to_record,
    kill_switch_to_incident_record,
    order_intent_to_record,
    pnl_to_record,
    position_to_record,
    reconciliation_to_record,
    risk_check_to_record,
)
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
from degenking.reconciliation.service import (
    ReconciliationDiscrepancy,
    ReconciliationDiscrepancyType,
    ReconciliationResult,
    ReconciliationStatus,
)
from degenking.risk.kill_switch import KillSwitchDecision, KillSwitchTrigger
from degenking.risk.pre_trade import RiskCheck, RiskCheckName

FROZEN_TIME = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# order_intent_to_record
# ---------------------------------------------------------------------------


def _make_order_intent(
    *,
    intent_id: str = "intent-1",
    trace_id: str = "trace-abc",
    run_id: str = "run-xyz",
    strategy_id: str = "strat-1",
    config_hash: str = "cfg-aaa",
    idempotency_key: str = "idem-1",
    symbol: str = "BTCUSDT",
    leg: OrderIntentLeg = OrderIntentLeg.SPOT_OPEN,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.01"),
    notional_quote: Decimal = Decimal("500"),
    limit_price: Decimal = Decimal("50000"),
    client_order_id: str = "client-1",
    state: OrderIntentState = OrderIntentState.ACKNOWLEDGED,
    exchange_order_id: str | None = None,
    filled_quantity: Decimal = Decimal("0"),
) -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id,
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
        client_order_id=client_order_id,
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        state=state,
        exchange_order_id=exchange_order_id,
        filled_quantity=filled_quantity,
    )


def test_order_intent_to_record_maps_key_fields() -> None:
    intent = _make_order_intent()
    record = order_intent_to_record(intent, "rec-1")

    assert isinstance(record, OrderIntentRecord)
    assert record.id == "rec-1"
    assert record.trace_id == "trace-abc"
    assert record.run_id == "run-xyz"
    assert record.strategy_id == "strat-1"
    assert record.config_hash == "cfg-aaa"
    assert record.idempotency_key == "idem-1"
    assert record.client_order_id == "client-1"
    assert record.exchange_order_id is None
    assert record.leg == "spot_open"
    assert record.side == "buy"
    assert record.symbol == "BTCUSDT"
    assert record.quantity == Decimal("0.01")
    assert record.limit_price == Decimal("50000")
    assert record.state == "acknowledged"
    assert record.filled_quantity == Decimal("0")


def test_order_intent_to_record_with_exchange_order_id() -> None:
    intent = _make_order_intent(exchange_order_id="exch-123")
    record = order_intent_to_record(intent, "rec-2")

    assert record.exchange_order_id == "exch-123"


def test_order_intent_to_record_decimal_values_remain_decimal() -> None:
    intent = _make_order_intent(
        quantity=Decimal("0.001"),
        limit_price=Decimal("50000.50"),
        filled_quantity=Decimal("0.0005"),
    )
    record = order_intent_to_record(intent, "rec-3")

    assert isinstance(record.quantity, Decimal)
    assert isinstance(record.limit_price, Decimal)
    assert isinstance(record.filled_quantity, Decimal)
    assert record.quantity == Decimal("0.001")
    assert record.filled_quantity == Decimal("0.0005")


# ---------------------------------------------------------------------------
# fill_to_record
# ---------------------------------------------------------------------------


def _make_fill(
    *,
    intent_id: str = "intent-1",
    symbol: str = "BTCUSDT",
    side: OrderSide = OrderSide.BUY,
    status: PaperFillStatus = PaperFillStatus.FULL_FILL,
    filled_quantity: Decimal = Decimal("0.01"),
    remaining_quantity: Decimal = Decimal("0"),
    filled_notional_quote: Decimal = Decimal("500"),
    average_price: Decimal | None = Decimal("50000"),
    fee_quote: Decimal = Decimal("3.0"),
    slippage_quote: Decimal = Decimal("2.0"),
    slippage_bps: Decimal = Decimal("4.0"),
    levels_consumed: int = 2,
    fully_filled: bool = True,
) -> PaperFillResult:
    return PaperFillResult(
        intent_id=intent_id,
        symbol=symbol,
        side=side,
        status=status,
        filled_quantity=filled_quantity,
        remaining_quantity=remaining_quantity,
        filled_notional_quote=filled_notional_quote,
        average_price=average_price,
        fee_quote=fee_quote,
        slippage_quote=slippage_quote,
        slippage_bps=slippage_bps,
        levels_consumed=levels_consumed,
        fully_filled=fully_filled,
    )


def test_fill_to_record_maps_key_fields() -> None:
    fill = _make_fill()
    record = fill_to_record(fill, "rec-fill-1", order_id="ord-1")

    assert isinstance(record, FillRecord)
    assert record.id == "rec-fill-1"
    assert record.order_id == "ord-1"
    assert record.intent_id == "intent-1"
    assert record.symbol == "BTCUSDT"
    assert record.price == Decimal("50000")
    assert record.quantity == Decimal("0.01")
    assert record.fee == Decimal("3.0")
    assert record.liquidity == "taker"


def test_fill_to_record_without_order_id() -> None:
    fill = _make_fill()
    record = fill_to_record(fill, "rec-fill-2")

    assert record.order_id is None


def test_fill_to_record_with_none_average_price() -> None:
    fill = _make_fill(average_price=None)
    record = fill_to_record(fill, "rec-fill-3")

    assert record.price is None


def test_fill_to_record_decimal_values_remain_decimal() -> None:
    fill = _make_fill()
    record = fill_to_record(fill, "rec-fill-4")

    assert isinstance(record.quantity, Decimal)
    assert isinstance(record.fee, Decimal)
    assert record.fee == Decimal("3.0")


# ---------------------------------------------------------------------------
# position_to_record
# ---------------------------------------------------------------------------


def _make_position(
    *,
    symbol: str = "BTCUSDT",
    spot_quantity: Decimal = Decimal("0.01"),
    perp_quantity: Decimal = Decimal("-0.01"),
    spot_entry_notional_quote: Decimal = Decimal("500"),
    perp_entry_notional_quote: Decimal = Decimal("500"),
    fees_quote: Decimal = Decimal("3.0"),
    slippage_quote: Decimal = Decimal("1.5"),
    funding_pnl_quote: Decimal = Decimal("2.0"),
    opened_at: datetime | None = None,
    updated_at: datetime | None = None,
    state: PositionState = PositionState.OPEN,
) -> HedgedPosition:
    return HedgedPosition(
        symbol=symbol,
        spot_quantity=spot_quantity,
        perp_quantity=perp_quantity,
        spot_entry_notional_quote=spot_entry_notional_quote,
        perp_entry_notional_quote=perp_entry_notional_quote,
        fees_quote=fees_quote,
        slippage_quote=slippage_quote,
        funding_pnl_quote=funding_pnl_quote,
        opened_at=opened_at or FROZEN_TIME,
        updated_at=updated_at or FROZEN_TIME,
        state=state,
    )


def test_position_to_record_maps_key_fields() -> None:
    pos = _make_position()
    record = position_to_record(pos, "rec-pos-1")

    assert isinstance(record, PositionRecord)
    assert record.id == "rec-pos-1"
    assert record.symbol == "BTCUSDT"
    assert record.spot_quantity == Decimal("0.01")
    assert record.perp_quantity == Decimal("-0.01")
    assert record.delta_quantity == Decimal("0")
    assert record.spot_entry_notional == Decimal("500")
    assert record.perp_entry_notional == Decimal("500")
    assert record.fees_quote == Decimal("3.0")
    assert record.slippage_quote == Decimal("1.5")
    assert record.funding_pnl_quote == Decimal("2.0")
    assert record.state == "open"


def test_position_to_record_computes_delta_quantity() -> None:
    pos = _make_position(
        spot_quantity=Decimal("0.02"),
        perp_quantity=Decimal("-0.01"),
    )
    record = position_to_record(pos, "rec-pos-2")

    assert record.delta_quantity == Decimal("0.01")


def test_position_to_record_decimal_values_remain_decimal() -> None:
    pos = _make_position()
    record = position_to_record(pos, "rec-pos-3")

    assert isinstance(record.spot_quantity, Decimal)
    assert isinstance(record.perp_quantity, Decimal)
    assert isinstance(record.delta_quantity, Decimal)
    assert isinstance(record.fees_quote, Decimal)


def test_position_to_record_sets_closed_at_for_closed_position() -> None:
    pos = _make_position(state=PositionState.CLOSED)
    record = position_to_record(pos, "rec-pos-4")

    assert record.closed_at == FROZEN_TIME


# ---------------------------------------------------------------------------
# pnl_to_record
# ---------------------------------------------------------------------------


def _make_pnl(
    *,
    symbol: str = "BTCUSDT",
    funding_pnl_quote: Decimal = Decimal("5.0"),
    fees_quote: Decimal = Decimal("3.0"),
    slippage_quote: Decimal = Decimal("1.0"),
    total_pnl_quote: Decimal = Decimal("2.0"),
    delta_quantity: Decimal = Decimal("0.001"),
    delta_notional_quote: Decimal = Decimal("50.0"),
) -> PositionPnL:
    return PositionPnL(
        symbol=symbol,
        spot_market_value_quote=Decimal("500"),
        perp_mark_value_quote=Decimal("500"),
        spot_unrealized_pnl_quote=Decimal("10"),
        perp_unrealized_pnl_quote=Decimal("-5"),
        funding_pnl_quote=funding_pnl_quote,
        fees_quote=fees_quote,
        slippage_quote=slippage_quote,
        total_pnl_quote=total_pnl_quote,
        delta_quantity=delta_quantity,
        delta_notional_quote=delta_notional_quote,
    )


def test_pnl_to_record_maps_key_fields() -> None:
    pnl = _make_pnl()
    record = pnl_to_record(pnl, "rec-pnl-1", position_id="pos-1")

    assert isinstance(record, PnlRecord)
    assert record.id == "rec-pnl-1"
    assert record.symbol == "BTCUSDT"
    assert record.position_id == "pos-1"
    assert record.funding_pnl == Decimal("5.0")
    assert record.trading_fees == Decimal("3.0")
    assert record.slippage_cost == Decimal("1.0")
    assert record.total_pnl == Decimal("2.0")
    assert record.unrealized_pnl == Decimal("5")
    assert record.realized_pnl == Decimal("0")


def test_pnl_to_record_without_position_id() -> None:
    pnl = _make_pnl()
    record = pnl_to_record(pnl, "rec-pnl-2")

    assert record.position_id is None


def test_pnl_to_record_decimal_values_remain_decimal() -> None:
    pnl = _make_pnl()
    record = pnl_to_record(pnl, "rec-pnl-3")

    assert isinstance(record.total_pnl, Decimal)
    assert isinstance(record.funding_pnl, Decimal)
    assert isinstance(record.trading_fees, Decimal)
    assert isinstance(record.slippage_cost, Decimal)


# ---------------------------------------------------------------------------
# reconciliation_to_record
# ---------------------------------------------------------------------------


def _make_reconciliation(
    *,
    symbol: str = "BTCUSDT",
    status: ReconciliationStatus = ReconciliationStatus.CLEAN,
    discrepancies: tuple[ReconciliationDiscrepancy, ...] = (),
    manual_recovery_required: bool = False,
) -> ReconciliationResult:
    return ReconciliationResult(
        symbol=symbol,
        status=status,
        discrepancies=discrepancies,
        expected_position=None,
        observed_position=HedgedPosition(
            symbol=symbol,
            spot_quantity=Decimal("0"),
            perp_quantity=Decimal("0"),
            spot_entry_notional_quote=Decimal("0"),
            perp_entry_notional_quote=Decimal("0"),
            fees_quote=Decimal("0"),
            slippage_quote=Decimal("0"),
            funding_pnl_quote=Decimal("0"),
            opened_at=FROZEN_TIME,
            updated_at=FROZEN_TIME,
            state=PositionState.CLOSED,
        ),
        reconciled_at=FROZEN_TIME,
        manual_recovery_required=manual_recovery_required,
    )


def test_reconciliation_to_record_clean() -> None:
    result = _make_reconciliation()
    record = reconciliation_to_record(result, "rec-recon-1")

    assert isinstance(record, ReconciliationRunRecord)
    assert record.id == "rec-recon-1"
    assert record.symbol == "BTCUSDT"
    assert record.status == "clean"
    assert record.discrepancy_count == 0
    assert record.discrepancies is None
    assert record.manual_recovery_required is False


def test_reconciliation_to_record_dirty_with_discrepancies() -> None:
    result = _make_reconciliation(
        status=ReconciliationStatus.DIRTY,
        discrepancies=(
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.FILL_WITHOUT_INTENT,
                entity_id="fill-99",
                expected="matching_intent",
                observed="missing",
                reason="fill_has_no_matching_intent",
            ),
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.POSITION_QUANTITY_MISMATCH,
                entity_id="BTCUSDT",
                expected="0.01",
                observed="0.005",
                reason="spot_quantity_mismatch",
            ),
        ),
        manual_recovery_required=True,
    )
    record = reconciliation_to_record(result, "rec-recon-2")

    assert record.status == "dirty"
    assert record.discrepancy_count == 2
    assert record.manual_recovery_required is True
    assert record.discrepancies is not None
    assert "fill_without_intent" in record.discrepancies
    assert "position_quantity_mismatch" in record.discrepancies


# ---------------------------------------------------------------------------
# risk_check_to_record
# ---------------------------------------------------------------------------


def test_risk_check_to_record_maps_key_fields() -> None:
    check = RiskCheck(
        name=RiskCheckName.KILL_SWITCH,
        passed=False,
        observed_value="true",
        limit_value="false",
        reason="kill_switch_active",
    )
    record = risk_check_to_record(check, "rec-rc-1", decision_id="dec-1")

    assert isinstance(record, RiskCheckRecord)
    assert record.id == "rec-rc-1"
    assert record.decision_id == "dec-1"
    assert record.check_name == "kill_switch"
    assert record.passed is False
    assert record.observed_value == "true"
    assert record.limit_value == "false"
    assert record.reason == "kill_switch_active"


def test_risk_check_to_record_passed_without_reason() -> None:
    check = RiskCheck(
        name=RiskCheckName.STRATEGY_SIGNAL,
        passed=True,
        observed_value="pass",
    )
    record = risk_check_to_record(check, "rec-rc-2")

    assert record.passed is True
    assert record.reason is None
    assert record.limit_value is None


def test_risk_check_to_record_without_decision_id() -> None:
    check = RiskCheck(
        name=RiskCheckName.SLIPPAGE,
        passed=True,
        observed_value="3.0",
    )
    record = risk_check_to_record(check, "rec-rc-3")

    assert record.decision_id is None


# ---------------------------------------------------------------------------
# kill_switch_to_incident_record
# ---------------------------------------------------------------------------


def test_kill_switch_active_maps_to_incident() -> None:
    decision = KillSwitchDecision(
        active=True,
        mode=KillSwitchMode.SIMULATED,
        triggers=(
            KillSwitchTrigger.DAILY_LOSS_LIMIT,
            KillSwitchTrigger.CONFIG_ENABLED,
        ),
        block_new_entries=True,
        simulate_cancel_close=True,
        enforce_cancel_close=False,
        manual_reset_required=True,
        reason="config_enabled;daily_loss_limit",
    )
    record = kill_switch_to_incident_record(decision, "rec-ks-1")

    assert record is not None
    assert isinstance(record, RiskIncidentRecord)
    assert record.id == "rec-ks-1"
    assert record.incident_type == "kill_switch"
    assert record.severity == "critical"
    assert record.trigger is not None
    assert "daily_loss_limit" in record.trigger
    assert "config_enabled" in record.trigger
    assert record.action_taken == "block_new_entries"
    assert record.manual_reset_required is True


def test_kill_switch_inactive_returns_none() -> None:
    decision = KillSwitchDecision(
        active=False,
        mode=KillSwitchMode.SIMULATED,
        triggers=(),
        block_new_entries=False,
        simulate_cancel_close=False,
        enforce_cancel_close=False,
        manual_reset_required=False,
        reason=None,
    )
    record = kill_switch_to_incident_record(decision, "rec-ks-2")

    assert record is None


def test_kill_switch_active_without_manual_reset() -> None:
    decision = KillSwitchDecision(
        active=True,
        mode=KillSwitchMode.ENFORCE,
        triggers=(KillSwitchTrigger.EXCHANGE_CRITICAL,),
        block_new_entries=True,
        simulate_cancel_close=False,
        enforce_cancel_close=True,
        manual_reset_required=False,
        reason="exchange_critical",
    )
    record = kill_switch_to_incident_record(decision, "rec-ks-3")

    assert record is not None
    assert record.manual_reset_required is False


# ---------------------------------------------------------------------------
# audit_event_to_system_event_record
# ---------------------------------------------------------------------------


def test_audit_event_to_system_event_record_maps_key_fields() -> None:
    event = AuditEvent(
        event_type="kill_switch_triggered",
        component="risk_engine",
        payload={"trigger": "daily_loss_limit", "pnl_pct": -2.5},
        trace_id="trace-evt-1",
        run_id="run-evt-1",
        strategy_id="strat-evt-1",
        config_hash="cfg-hash-1",
        severity=EventSeverity.CRITICAL,
        created_at=FROZEN_TIME,
    )
    record = audit_event_to_system_event_record(event, "rec-se-1")

    assert isinstance(record, SystemEventRecord)
    assert record.id == "rec-se-1"
    assert record.trace_id == "trace-evt-1"
    assert record.run_id == "run-evt-1"
    assert record.strategy_id == "strat-evt-1"
    assert record.config_hash == "cfg-hash-1"
    assert record.component == "risk_engine"
    assert record.severity == "critical"
    assert record.event_type == "kill_switch_triggered"
    assert record.message is None
    assert record.payload is not None
    assert "daily_loss_limit" in record.payload


def test_audit_event_to_system_event_record_info_severity() -> None:
    event = AuditEvent(
        event_type="position_update",
        component="position_manager",
        payload={"symbol": "BTCUSDT", "state": "open"},
        severity=EventSeverity.INFO,
        created_at=FROZEN_TIME,
    )
    record = audit_event_to_system_event_record(event, "rec-se-2")

    assert record.severity == "info"


# ---------------------------------------------------------------------------
# Record immutability
# ---------------------------------------------------------------------------


def test_mapped_records_are_frozen() -> None:
    intent = _make_order_intent()
    record = order_intent_to_record(intent, "rec-frz")

    raised = False
    try:
        record.symbol = "ETHUSDT"  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# No forbidden imports
# ---------------------------------------------------------------------------


def test_persistence_mappers_has_no_forbidden_imports() -> None:
    import ast
    from pathlib import Path

    path = Path("src/degenking/persistence/mappers.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden = frozenset({
        "degenking.paper.broker",
        "degenking.orders.state_machine",
        "degenking.risk.engine",
        "degenking.risk.execution_guards",
        "sqlalchemy",
        "psycopg2",
        "requests",
        "httpx",
    })

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, (
                    f"forbidden import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module not in forbidden, (
                f"forbidden import: {node.module}"
            )
