"""Tests for reporting summary pure functions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from degenking.common.enums import KillSwitchMode
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
from degenking.reporting.summaries import (
    summarize_kill_switch,
    summarize_opportunity_evaluation,
    summarize_position_pnl,
    summarize_reconciliation,
    summarize_risk_decision,
    summarize_startup_recovery,
)
from degenking.risk.kill_switch import KillSwitchDecision, KillSwitchTrigger
from degenking.risk.pre_trade import (
    PreTradeRiskDecision,
    RiskCheck,
    RiskCheckName,
)
from degenking.strategy.models import (
    FundingArbitrageEdge,
    FundingArbitrageSignal,
)
from degenking.strategy.opportunity import OpportunityEvaluation

FROZEN_TIME = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Forbidden field check (shared across all summaries)
# ---------------------------------------------------------------------------

FORBIDDEN_FIELDS = frozenset({
    "order_command",
    "cancel_command",
    "leverage_change",
    "risk_override",
    "live_config_mutation",
})


def _assert_no_forbidden_fields(result: dict[str, object]) -> None:
    keys = set(result.keys())
    overlap = keys & FORBIDDEN_FIELDS
    assert not overlap, f"forbidden fields in summary: {overlap}"


# ---------------------------------------------------------------------------
# summarize_risk_decision
# ---------------------------------------------------------------------------


def test_summarize_risk_decision_approved() -> None:
    decision = PreTradeRiskDecision(
        approved=True,
        checks=(
            RiskCheck(
                name=RiskCheckName.STRATEGY_SIGNAL,
                passed=True,
                observed_value="pass",
            ),
            RiskCheck(
                name=RiskCheckName.KILL_SWITCH,
                passed=True,
                observed_value="false",
            ),
        ),
    )
    result = summarize_risk_decision(decision)

    assert result["approved"] is True
    assert result["failed_checks"] == ()
    assert result["rejection_reasons"] == ()
    _assert_no_forbidden_fields(result)


def test_summarize_risk_decision_rejected() -> None:
    decision = PreTradeRiskDecision(
        approved=False,
        checks=(
            RiskCheck(
                name=RiskCheckName.STRATEGY_SIGNAL,
                passed=False,
                observed_value="signal_rejected",
                reason="strategy_signal_rejected",
            ),
            RiskCheck(
                name=RiskCheckName.SLIPPAGE,
                passed=False,
                observed_value="15.0",
                limit_value="10.0",
                reason="slippage_or_fill_depth_exceeds_limit",
            ),
            RiskCheck(
                name=RiskCheckName.KILL_SWITCH,
                passed=True,
                observed_value="false",
            ),
        ),
    )
    result = summarize_risk_decision(decision)

    assert result["approved"] is False
    assert result["failed_checks"] == ("strategy_signal", "slippage")
    assert result["rejection_reasons"] == (
        "strategy_signal_rejected",
        "slippage_or_fill_depth_exceeds_limit",
    )
    _assert_no_forbidden_fields(result)


def test_summarize_risk_decision_failed_check_no_reason_falls_back_to_name() -> None:
    decision = PreTradeRiskDecision(
        approved=False,
        checks=(
            RiskCheck(
                name=RiskCheckName.EXCHANGE_STATUS,
                passed=False,
                observed_value="degraded",
            ),
        ),
    )
    result = summarize_risk_decision(decision)

    assert result["rejection_reasons"] == ("exchange_status",)
    _assert_no_forbidden_fields(result)


# ---------------------------------------------------------------------------
# summarize_opportunity_evaluation
# ---------------------------------------------------------------------------


def _make_opportunity_evaluation(
    *,
    should_enter: bool = True,
    risk_approved: bool = True,
    net_edge_quote: Decimal = Decimal("2.5"),
    net_edge_bps: Decimal = Decimal("5.0"),
    funding_rate_bps: Decimal = Decimal("10.0"),
    reasons: tuple[str, ...] = (),
    failed_checks: tuple[str, ...] = (),
) -> OpportunityEvaluation:
    checks = [
        RiskCheck(
            name=RiskCheckName.STRATEGY_SIGNAL,
            passed=True,
            observed_value="pass",
        ),
    ]
    for name in failed_checks:
        checks.append(
            RiskCheck(
                name=RiskCheckName(name),
                passed=False,
                observed_value="fail",
                reason=name,
            )
        )
    if not risk_approved:
        checks.append(
            RiskCheck(
                name=RiskCheckName.KILL_SWITCH,
                passed=False,
                observed_value="true",
                reason="kill_switch_active",
            )
        )

    edge = FundingArbitrageEdge(
        expected_funding_income=Decimal("8.0"),
        opening_fees=Decimal("3.0"),
        closing_fees=Decimal("1.5"),
        entry_slippage=Decimal("0.5"),
        exit_slippage=Decimal("0.5"),
        funding_uncertainty_buffer=Decimal("0"),
        basis_adverse_move_buffer=Decimal("0"),
        residual_delta_buffer=Decimal("0"),
        net_edge_quote=net_edge_quote,
        net_edge_bps=net_edge_bps,
        funding_rate_bps=funding_rate_bps,
        basis_bps=Decimal("3.0"),
        seconds_to_funding=1800,
    )
    signal = FundingArbitrageSignal(
        symbol="BTCUSDT",
        should_enter=should_enter,
        edge=edge,
        reasons=reasons,
    )
    risk_decision = PreTradeRiskDecision(
        approved=risk_approved,
        checks=tuple(checks),
    )
    return OpportunityEvaluation(
        symbol="BTCUSDT",
        signal=signal,
        risk_decision=risk_decision,
        strategy_inputs=None,  # type: ignore[arg-type]
        spot_precision=None,  # type: ignore[arg-type]
        perp_precision=None,  # type: ignore[arg-type]
        entry_spot_slippage=None,  # type: ignore[arg-type]
        entry_perp_slippage=None,  # type: ignore[arg-type]
        exit_spot_slippage=None,  # type: ignore[arg-type]
        exit_perp_slippage=None,  # type: ignore[arg-type]
        freshness=(),
        latency=None,  # type: ignore[arg-type]
    )


def test_summarize_opportunity_evaluation() -> None:
    evaluation = _make_opportunity_evaluation(
        reasons=("funding_rate_above_threshold", "net_edge_positive"),
    )
    result = summarize_opportunity_evaluation(evaluation)

    assert result["symbol"] == "BTCUSDT"
    assert result["should_enter"] is True
    assert result["risk_approved"] is True
    assert result["net_edge_quote"] == "2.5"
    assert result["net_edge_bps"] == "5"
    assert result["funding_rate_bps"] == "10"
    assert result["reasons"] == ("funding_rate_above_threshold", "net_edge_positive")
    assert result["failed_risk_checks"] == ()
    _assert_no_forbidden_fields(result)


def test_summarize_opportunity_evaluation_with_failed_risk_checks() -> None:
    evaluation = _make_opportunity_evaluation(
        risk_approved=False,
        failed_checks=("slippage", "precision"),
    )
    result = summarize_opportunity_evaluation(evaluation)

    assert result["risk_approved"] is False
    assert set(result["failed_risk_checks"]) == {"slippage", "precision", "kill_switch"}
    _assert_no_forbidden_fields(result)


# ---------------------------------------------------------------------------
# summarize_position_pnl
# ---------------------------------------------------------------------------


def test_summarize_position_pnl() -> None:
    pnl = PositionPnL(
        symbol="BTCUSDT",
        spot_market_value_quote=Decimal("50000.0"),
        perp_mark_value_quote=Decimal("50000.0"),
        spot_unrealized_pnl_quote=Decimal("10.0"),
        perp_unrealized_pnl_quote=Decimal("-5.0"),
        funding_pnl_quote=Decimal("15.5"),
        fees_quote=Decimal("3.0"),
        slippage_quote=Decimal("1.25"),
        total_pnl_quote=Decimal("21.25"),
        delta_quantity=Decimal("0.001"),
        delta_notional_quote=Decimal("50.0"),
    )
    result = summarize_position_pnl(pnl)

    assert result["symbol"] == "BTCUSDT"
    assert result["total_pnl_quote"] == "21.25"
    assert result["funding_pnl_quote"] == "15.5"
    assert result["fees_quote"] == "3"
    assert result["slippage_quote"] == "1.25"
    assert result["delta_quantity"] == "0.001"
    assert result["delta_notional_quote"] == "50"
    _assert_no_forbidden_fields(result)


def test_summarize_position_pnl_negative_values() -> None:
    pnl = PositionPnL(
        symbol="ETHUSDT",
        spot_market_value_quote=Decimal("3000.0"),
        perp_mark_value_quote=Decimal("3000.0"),
        spot_unrealized_pnl_quote=Decimal("-20.0"),
        perp_unrealized_pnl_quote=Decimal("-10.0"),
        funding_pnl_quote=Decimal("5.0"),
        fees_quote=Decimal("2.0"),
        slippage_quote=Decimal("0.5"),
        total_pnl_quote=Decimal("-27.5"),
        delta_quantity=Decimal("-0.01"),
        delta_notional_quote=Decimal("-30.0"),
    )
    result = summarize_position_pnl(pnl)

    assert result["total_pnl_quote"] == "-27.5"
    assert result["delta_quantity"] == "-0.01"
    assert result["delta_notional_quote"] == "-30"
    _assert_no_forbidden_fields(result)


# ---------------------------------------------------------------------------
# summarize_reconciliation
# ---------------------------------------------------------------------------


def test_summarize_reconciliation_clean() -> None:
    result = ReconciliationResult(
        symbol="BTCUSDT",
        status=ReconciliationStatus.CLEAN,
        discrepancies=(),
        expected_position=HedgedPosition(
            symbol="BTCUSDT",
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
        observed_position=HedgedPosition(
            symbol="BTCUSDT",
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
        manual_recovery_required=False,
    )
    summary = summarize_reconciliation(result)

    assert summary["symbol"] == "BTCUSDT"
    assert summary["status"] == "clean"
    assert summary["discrepancy_count"] == 0
    assert summary["discrepancy_types"] == ()
    assert summary["manual_recovery_required"] is False
    _assert_no_forbidden_fields(summary)


def test_summarize_reconciliation_dirty() -> None:
    result = ReconciliationResult(
        symbol="ETHUSDT",
        status=ReconciliationStatus.DIRTY,
        discrepancies=(
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.FILL_WITHOUT_INTENT,
                entity_id="fill-1",
                expected="matching_intent",
                observed="missing",
                reason="fill_has_no_matching_intent",
            ),
            ReconciliationDiscrepancy(
                type=ReconciliationDiscrepancyType.POSITION_QUANTITY_MISMATCH,
                entity_id="ETHUSDT",
                expected="0.1",
                observed="0.05",
                reason="spot_quantity_mismatch",
            ),
        ),
        expected_position=None,
        observed_position=HedgedPosition(
            symbol="ETHUSDT",
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
        manual_recovery_required=True,
    )
    summary = summarize_reconciliation(result)

    assert summary["symbol"] == "ETHUSDT"
    assert summary["status"] == "dirty"
    assert summary["discrepancy_count"] == 2
    assert summary["discrepancy_types"] == (
        "fill_without_intent",
        "position_quantity_mismatch",
    )
    assert summary["manual_recovery_required"] is True
    _assert_no_forbidden_fields(summary)


# ---------------------------------------------------------------------------
# summarize_startup_recovery
# ---------------------------------------------------------------------------


def test_summarize_startup_recovery_allowed() -> None:
    decision = StartupRecoveryDecision(
        action=StartupRecoveryAction.ALLOW_NEW_ENTRIES,
        issues=(),
        evaluated_at=FROZEN_TIME,
    )
    result = summarize_startup_recovery(decision)

    assert result["action"] == "allow_new_entries"
    assert result["new_entries_allowed"] is True
    assert result["manual_recovery_required"] is False
    assert result["issue_count"] == 0
    assert result["issue_types"] == ()
    _assert_no_forbidden_fields(result)


def test_summarize_startup_recovery_blocked() -> None:
    decision = StartupRecoveryDecision(
        action=StartupRecoveryAction.BLOCK_NEW_ENTRIES,
        issues=(
            StartupRecoveryIssue(
                type=StartupRecoveryIssueType.OPEN_INTENT,
                entity_id="intent-1",
                reason="non_terminal_intent_loaded_at_startup",
            ),
            StartupRecoveryIssue(
                type=StartupRecoveryIssueType.OPEN_POSITION,
                entity_id="BTCUSDT",
                reason="open_position_loaded_at_startup",
            ),
        ),
        evaluated_at=FROZEN_TIME,
    )
    result = summarize_startup_recovery(decision)

    assert result["action"] == "block_new_entries"
    assert result["new_entries_allowed"] is False
    assert result["manual_recovery_required"] is False
    assert result["issue_count"] == 2
    assert result["issue_types"] == ("open_intent", "open_position")
    _assert_no_forbidden_fields(result)


def test_summarize_startup_recovery_manual_recovery() -> None:
    decision = StartupRecoveryDecision(
        action=StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY,
        issues=(
            StartupRecoveryIssue(
                type=StartupRecoveryIssueType.DIRTY_RECONCILIATION,
                entity_id="ETHUSDT",
                reason="dirty_reconciliation_result_loaded_at_startup",
            ),
        ),
        evaluated_at=FROZEN_TIME,
    )
    result = summarize_startup_recovery(decision)

    assert result["action"] == "require_manual_recovery"
    assert result["new_entries_allowed"] is False
    assert result["manual_recovery_required"] is True
    assert result["issue_count"] == 1
    assert result["issue_types"] == ("dirty_reconciliation",)
    _assert_no_forbidden_fields(result)


# ---------------------------------------------------------------------------
# summarize_kill_switch
# ---------------------------------------------------------------------------


def test_summarize_kill_switch_active() -> None:
    decision = KillSwitchDecision(
        active=True,
        mode=KillSwitchMode.SIMULATED,
        triggers=(
            KillSwitchTrigger.CONFIG_ENABLED,
            KillSwitchTrigger.DAILY_LOSS_LIMIT,
        ),
        block_new_entries=True,
        simulate_cancel_close=True,
        enforce_cancel_close=False,
        manual_reset_required=True,
        reason="config_enabled;daily_loss_limit",
    )
    result = summarize_kill_switch(decision)

    assert result["active"] is True
    assert result["mode"] == "simulated"
    assert result["triggers"] == ("config_enabled", "daily_loss_limit")
    assert result["block_new_entries"] is True
    assert result["simulate_cancel_close"] is True
    assert result["enforce_cancel_close"] is False
    assert result["manual_reset_required"] is True
    assert result["reason"] == "config_enabled;daily_loss_limit"
    _assert_no_forbidden_fields(result)


def test_summarize_kill_switch_inactive() -> None:
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
    result = summarize_kill_switch(decision)

    assert result["active"] is False
    assert result["triggers"] == ()
    assert result["reason"] is None
    _assert_no_forbidden_fields(result)


# ---------------------------------------------------------------------------
# Forbidden imports: reporting.summaries must not import from
# broker / exchange / execution / order state machine
# ---------------------------------------------------------------------------

def test_reporting_summaries_has_no_forbidden_imports() -> None:
    import ast
    from pathlib import Path

    path = Path("src/degenking/reporting/summaries.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden = frozenset({
        "degenking.paper.broker",
        "degenking.paper.fill_model",
        "degenking.orders.intents",
        "degenking.orders.state_machine",
        "degenking.orders.idempotency",
        "degenking.risk.execution_guards",
        "degenking.risk.engine",
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
