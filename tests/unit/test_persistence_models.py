"""Tests for persistence model contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from degenking.persistence.models import (
    AccountSnapshotRecord,
    AgentReportRecord,
    BalanceSnapshotRecord,
    BaseRecord,
    ConfigVersionRecord,
    ExchangeStatusRecord,
    FillRecord,
    FundingRateRecord,
    LatencySampleRecord,
    ManualActionRecord,
    MarketTickRecord,
    OrderBookSnapshotRecord,
    OrderIntentRecord,
    OrderRecord,
    PnlRecord,
    PositionRecord,
    RawExchangeEventRecord,
    ReconciliationRunRecord,
    RiskCheckRecord,
    RiskIncidentRecord,
    SignalRecord,
    SystemEventRecord,
    record_identity,
    require_non_empty,
)

FROZEN_TIME = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

COMMON_FIELDS = frozenset({
    "id",
    "trace_id",
    "run_id",
    "strategy_id",
    "config_hash",
    "created_at",
    "updated_at",
})

ALL_RECORD_TYPES = (
    ConfigVersionRecord,
    ExchangeStatusRecord,
    LatencySampleRecord,
    MarketTickRecord,
    OrderBookSnapshotRecord,
    FundingRateRecord,
    AccountSnapshotRecord,
    BalanceSnapshotRecord,
    SignalRecord,
    RiskCheckRecord,
    RiskIncidentRecord,
    OrderIntentRecord,
    OrderRecord,
    FillRecord,
    PositionRecord,
    PnlRecord,
    ReconciliationRunRecord,
    ManualActionRecord,
    AgentReportRecord,
    SystemEventRecord,
    RawExchangeEventRecord,
)


# ---------------------------------------------------------------------------
# Common fields existence
# ---------------------------------------------------------------------------


def _field_names(record_type: type[BaseRecord]) -> frozenset[str]:
    return frozenset(record_type.__dataclass_fields__.keys())  # type: ignore[attr-defined]


def test_all_records_have_common_id_fields() -> None:
    for record_type in ALL_RECORD_TYPES:
        fields = _field_names(record_type)
        missing = COMMON_FIELDS - fields
        assert not missing, f"{record_type.__name__} missing common fields: {missing}"


# ---------------------------------------------------------------------------
# Construction: every record type can be instantiated
# ---------------------------------------------------------------------------


def test_config_version_record_construction() -> None:
    r = ConfigVersionRecord(
        id="cv-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        mode="paper",
        exchange="binance",
        symbols=("BTCUSDT", "ETHUSDT"),
        raw_config="mode: paper\n...",
        validation_status="valid",
        validation_result="ok",
        config_hash="abc123",
    )
    assert r.mode == "paper"
    assert r.symbols == ("BTCUSDT", "ETHUSDT")
    assert r.config_hash == "abc123"
    assert r.raw_config is not None
    assert r.validation_result == "ok"
    assert record_identity(r)[0] == "ConfigVersionRecord"


def test_exchange_status_record_construction() -> None:
    r = ExchangeStatusRecord(
        id="es-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        exchange="binance",
        environment="testnet",
        status="ok",
        maintenance=False,
    )
    assert r.exchange == "binance"
    assert r.status == "ok"
    assert r.maintenance is False


def test_latency_sample_record_construction() -> None:
    r = LatencySampleRecord(
        id="ls-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        exchange="binance",
        channel="ticker",
        latency_ms=42,
    )
    assert r.latency_ms == 42
    assert r.channel == "ticker"


def test_market_tick_record_construction() -> None:
    r = MarketTickRecord(
        id="mt-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        market_type="spot",
        bid=Decimal("50000.0"),
        ask=Decimal("50001.0"),
        mid=Decimal("50000.5"),
    )
    assert r.symbol == "BTCUSDT"
    assert r.bid == Decimal("50000.0")


def test_orderbook_snapshot_record_construction() -> None:
    r = OrderBookSnapshotRecord(
        id="ob-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        market_type="spot",
        bids='[["50000.0","1.5"],["49999.0","2.0"]]',
        asks='[["50001.0","1.5"],["50002.0","3.0"]]',
        depth_usd=Decimal("400000"),
    )
    assert r.symbol == "BTCUSDT"
    assert r.bids is not None
    assert r.asks is not None


def test_funding_rate_record_construction() -> None:
    r = FundingRateRecord(
        id="fr-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        funding_rate=Decimal("0.0001"),
        funding_interval_seconds=28800,
    )
    assert r.funding_rate == Decimal("0.0001")


def test_account_snapshot_record_construction() -> None:
    r = AccountSnapshotRecord(
        id="as-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        equity=Decimal("10000"),
        available_margin=Decimal("8000"),
        account_mode="cross",
    )
    assert r.equity == Decimal("10000")


def test_balance_snapshot_record_construction() -> None:
    r = BalanceSnapshotRecord(
        id="bs-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        asset="USDT",
        wallet_balance=Decimal("10000"),
        available_balance=Decimal("9000"),
        locked_balance=Decimal("1000"),
    )
    assert r.asset == "USDT"


def test_signal_record_construction() -> None:
    r = SignalRecord(
        id="sig-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        net_edge_quote=Decimal("2.5"),
        net_edge_bps=Decimal("5.0"),
        suggested_notional=Decimal("500"),
        status="approved",
        reasons=("funding_rate_above_threshold", "net_edge_positive"),
    )
    assert r.status == "approved"
    assert len(r.reasons) == 2


def test_risk_check_record_construction() -> None:
    r = RiskCheckRecord(
        id="rc-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        decision_id="dec-1",
        check_name="kill_switch",
        passed=True,
        observed_value="false",
        limit_value="false",
    )
    assert r.passed is True
    assert r.check_name == "kill_switch"


def test_risk_incident_record_construction() -> None:
    r = RiskIncidentRecord(
        id="ri-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        incident_type="daily_loss_limit",
        severity="critical",
        trigger="daily_pnl_lt_neg_2pct",
        action_taken="block_new_entries",
        manual_reset_required=True,
    )
    assert r.severity == "critical"
    assert r.manual_reset_required is True


def test_order_intent_record_construction() -> None:
    r = OrderIntentRecord(
        id="oi-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        idempotency_key="idem-abc",
        client_order_id="client-123",
        exchange_order_id=None,
        leg="spot_open",
        side="buy",
        symbol="BTCUSDT",
        quantity=Decimal("0.01"),
        limit_price=Decimal("50000"),
        state="acknowledged",
        filled_quantity=Decimal("0"),
    )
    assert r.idempotency_key == "idem-abc"
    assert r.client_order_id == "client-123"
    assert r.exchange_order_id is None
    assert r.leg == "spot_open"
    assert r.side == "buy"
    assert r.state == "acknowledged"


def test_order_record_construction() -> None:
    r = OrderRecord(
        id="ord-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        client_order_id="client-123",
        exchange_order_id="exch-456",
        intent_id="oi-1",
        symbol="BTCUSDT",
        side="buy",
        quantity=Decimal("0.01"),
        limit_price=Decimal("50000"),
        state="filled",
    )
    assert r.exchange_order_id == "exch-456"
    assert r.intent_id == "oi-1"


def test_fill_record_construction() -> None:
    r = FillRecord(
        id="fill-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        order_id="ord-1",
        intent_id="oi-1",
        symbol="BTCUSDT",
        price=Decimal("50000"),
        quantity=Decimal("0.01"),
        fee=Decimal("1.5"),
        liquidity="taker",
    )
    assert r.price == Decimal("50000")
    assert r.liquidity == "taker"


def test_position_record_construction() -> None:
    r = PositionRecord(
        id="pos-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        spot_quantity=Decimal("0.01"),
        perp_quantity=Decimal("-0.01"),
        delta_quantity=Decimal("0"),
        spot_entry_notional=Decimal("500"),
        perp_entry_notional=Decimal("500"),
        entry_basis_bps=Decimal("5.0"),
        fees_quote=Decimal("3.0"),
        slippage_quote=Decimal("1.0"),
        funding_pnl_quote=Decimal("2.0"),
        state="open",
        opened_at=FROZEN_TIME,
    )
    assert r.symbol == "BTCUSDT"
    assert r.state == "open"


def test_pnl_record_construction() -> None:
    r = PnlRecord(
        id="pnl-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        position_id="pos-1",
        funding_pnl=Decimal("5.0"),
        trading_fees=Decimal("3.0"),
        slippage_cost=Decimal("1.0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("2.0"),
        total_pnl=Decimal("3.0"),
    )
    assert r.total_pnl == Decimal("3.0")
    assert r.position_id == "pos-1"


def test_reconciliation_run_record_construction() -> None:
    r = ReconciliationRunRecord(
        id="rec-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        status="dirty",
        discrepancy_count=2,
        manual_recovery_required=True,
    )
    assert r.status == "dirty"
    assert r.discrepancy_count == 2
    assert r.manual_recovery_required is True


def test_manual_action_record_construction() -> None:
    r = ManualActionRecord(
        id="ma-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        actor="operator",
        action="acknowledge_kill_switch",
        reason="daily_loss_limit_breach",
        affected_trace_id="trace-1",
    )
    assert r.actor == "operator"
    assert r.action == "acknowledge_kill_switch"


def test_agent_report_record_construction() -> None:
    r = AgentReportRecord(
        id="ar-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        report_type="risk_summary",
        source_views=("audit_events", "reporting_views"),
        content="All systems nominal.",
    )
    assert r.report_type == "risk_summary"
    assert r.source_views == ("audit_events", "reporting_views")


def test_system_event_record_construction() -> None:
    r = SystemEventRecord(
        id="se-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        component="risk_engine",
        severity="warning",
        event_type="kill_switch_triggered",
        message="Daily loss limit breached.",
        payload='{"pnl_pct": -2.5}',
    )
    assert r.component == "risk_engine"
    assert r.severity == "warning"


def test_raw_exchange_event_record_construction() -> None:
    r = RawExchangeEventRecord(
        id="re-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        source="binance_ws",
        channel="btcusdt@ticker",
        payload='{"e":"24hrTicker","s":"BTCUSDT","c":"50001.00"}',
    )
    assert r.source == "binance_ws"
    assert r.channel == "btcusdt@ticker"


# ---------------------------------------------------------------------------
# Key fields on specific record types
# ---------------------------------------------------------------------------


def test_order_intent_has_idempotency_and_order_id_fields() -> None:
    fields = _field_names(OrderIntentRecord)
    assert "idempotency_key" in fields
    assert "client_order_id" in fields
    assert "exchange_order_id" in fields


def test_reconciliation_run_has_discrepancy_and_recovery_fields() -> None:
    fields = _field_names(ReconciliationRunRecord)
    assert "discrepancy_count" in fields
    assert "manual_recovery_required" in fields


def test_config_version_has_hash_rawconfig_validation_fields() -> None:
    fields = _field_names(ConfigVersionRecord)
    assert "config_hash" in fields
    assert "raw_config" in fields
    assert "validation_result" in fields


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_records_are_frozen() -> None:
    r = SignalRecord(
        id="sig-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
        symbol="BTCUSDT",
        status="approved",
    )
    raised = False
    try:
        r.status = "rejected"  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_require_non_empty_passes_for_valid_string() -> None:
    result = require_non_empty("hello", "test_field")
    assert result == "hello"


def test_require_non_empty_raises_for_empty_string() -> None:
    with pytest.raises(ValueError, match="test_field must be non-empty"):
        require_non_empty("", "test_field")


def test_require_non_empty_raises_for_none() -> None:
    with pytest.raises(ValueError, match="test_field must be non-empty"):
        require_non_empty(None, "test_field")


def test_record_identity_returns_type_id_trace_id() -> None:
    r = ConfigVersionRecord(
        id="cv-1",
        trace_id="trace-abc",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
    )
    rec_type, rec_id, rec_trace = record_identity(r)
    assert rec_type == "ConfigVersionRecord"
    assert rec_id == "cv-1"
    assert rec_trace == "trace-abc"


def test_record_identity_none_trace_id() -> None:
    r = SignalRecord(
        id="sig-1",
        created_at=FROZEN_TIME,
        updated_at=FROZEN_TIME,
    )
    _rec_type, _rec_id, rec_trace = record_identity(r)
    assert rec_trace is None


# ---------------------------------------------------------------------------
# No forbidden imports from broker / exchange / order state machine
# ---------------------------------------------------------------------------


def test_persistence_models_has_no_forbidden_imports() -> None:
    import ast
    from pathlib import Path

    path = Path("src/degenking/persistence/models.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden = frozenset({
        "degenking.paper.broker",
        "degenking.paper.fill_model",
        "degenking.orders.intents",
        "degenking.orders.state_machine",
        "degenking.orders.idempotency",
        "degenking.risk.engine",
        "sqlalchemy",
        "psycopg2",
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
