from __future__ import annotations

from datetime import UTC, datetime

from degenking.common.enums import KillSwitchMode
from degenking.reconciliation.startup_recovery import (
    StartupRecoveryAction,
    StartupRecoveryDecision,
    StartupRecoveryIssue,
    StartupRecoveryIssueType,
)
from degenking.risk.engine import (
    RiskEngine,
    RiskEngineReason,
    aggregate_risk_decisions,
)
from degenking.risk.execution_guards import (
    ExecutionGuardDecision,
    ExecutionGuardReason,
)
from degenking.risk.kill_switch import KillSwitchDecision, KillSwitchTrigger
from degenking.risk.pre_trade import (
    PreTradeRiskDecision,
    RiskCheck,
    RiskCheckName,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_aggregate_all_clear_allows_new_entry() -> None:
    decision = aggregate_risk_decisions(
        pre_trade=_pre_trade(True),
        execution=_execution(True),
        kill_switch=_kill_switch(False),
        startup=_startup(StartupRecoveryAction.ALLOW_NEW_ENTRIES),
    )

    assert decision.allow_new_entry is True
    assert decision.block_symbol is False
    assert decision.block_global is False
    assert decision.manual_recovery_required is False
    assert decision.reasons == ()


def test_aggregate_pre_trade_rejection_blocks_symbol_only() -> None:
    decision = aggregate_risk_decisions(pre_trade=_pre_trade(False))

    assert decision.allow_new_entry is False
    assert decision.block_symbol is True
    assert decision.block_global is False
    assert decision.manual_recovery_required is False
    assert decision.reasons == (RiskEngineReason.PRE_TRADE_REJECTED,)
    assert decision.source_reasons == ("strategy_signal_rejected",)


def test_aggregate_execution_block_blocks_symbol() -> None:
    decision = aggregate_risk_decisions(
        execution=_execution(
            False,
            reasons=(ExecutionGuardReason.ORDER_TIMEOUT,),
            block_new_entries=True,
        )
    )

    assert decision.block_symbol is True
    assert decision.block_global is False
    assert decision.manual_recovery_required is False
    assert decision.reasons == (RiskEngineReason.EXECUTION_GUARD_BLOCK,)
    assert decision.source_reasons == ("order_timeout",)


def test_aggregate_execution_manual_recovery_requires_manual_recovery() -> None:
    decision = aggregate_risk_decisions(
        execution=_execution(
            False,
            reasons=(ExecutionGuardReason.RESIDUAL_EXPOSURE,),
            block_new_entries=True,
            manual_recovery_required=True,
        )
    )

    assert decision.block_symbol is True
    assert decision.manual_recovery_required is True
    assert RiskEngineReason.EXECUTION_GUARD_BLOCK in decision.reasons
    assert RiskEngineReason.EXECUTION_MANUAL_RECOVERY in decision.reasons


def test_aggregate_kill_switch_blocks_global() -> None:
    decision = aggregate_risk_decisions(
        kill_switch=_kill_switch(
            True,
            triggers=(KillSwitchTrigger.DAILY_LOSS_LIMIT,),
        )
    )

    assert decision.allow_new_entry is False
    assert decision.block_global is True
    assert decision.block_symbol is False
    assert decision.reasons == (RiskEngineReason.KILL_SWITCH_ACTIVE,)
    assert decision.source_reasons == ("daily_loss_limit",)


def test_aggregate_kill_switch_manual_reset_requires_manual_recovery() -> None:
    decision = aggregate_risk_decisions(
        kill_switch=_kill_switch(
            True,
            triggers=(KillSwitchTrigger.DAILY_LOSS_LIMIT,),
            manual_reset_required=True,
        )
    )

    assert decision.block_global is True
    assert decision.manual_recovery_required is True
    assert RiskEngineReason.KILL_SWITCH_MANUAL_RESET in decision.reasons


def test_aggregate_startup_block_blocks_symbol() -> None:
    decision = aggregate_risk_decisions(
        startup=_startup(
            StartupRecoveryAction.BLOCK_NEW_ENTRIES,
            issue_type=StartupRecoveryIssueType.OPEN_INTENT,
        )
    )

    assert decision.block_symbol is True
    assert decision.block_global is False
    assert decision.reasons == (RiskEngineReason.STARTUP_BLOCKED,)
    assert decision.source_reasons == ("startup_issue",)


def test_aggregate_startup_manual_recovery_blocks_global() -> None:
    decision = aggregate_risk_decisions(
        startup=_startup(
            StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY,
            issue_type=StartupRecoveryIssueType.DIRTY_RECONCILIATION,
        )
    )

    assert decision.block_global is True
    assert decision.manual_recovery_required is True
    assert decision.reasons == (RiskEngineReason.STARTUP_MANUAL_RECOVERY,)


def test_aggregate_multiple_layers_dedupes_source_reasons() -> None:
    decision = aggregate_risk_decisions(
        pre_trade=_pre_trade(False),
        execution=_execution(
            False,
            reasons=(ExecutionGuardReason.UNRECONCILED_STATE,),
            block_new_entries=True,
            manual_recovery_required=True,
        ),
        kill_switch=_kill_switch(
            True,
            triggers=(KillSwitchTrigger.RECONCILIATION_FAILURE,),
        ),
    )

    assert decision.allow_new_entry is False
    assert decision.block_symbol is True
    assert decision.block_global is True
    assert decision.manual_recovery_required is True
    assert decision.source_reasons == (
        "strategy_signal_rejected",
        "unreconciled_state",
        "reconciliation_failure",
    )


def test_risk_engine_facade_aggregates_decisions() -> None:
    decision = RiskEngine().aggregate(pre_trade=_pre_trade(False))

    assert decision.allow_new_entry is False
    assert decision.pre_trade_approved is False


def _pre_trade(approved: bool) -> PreTradeRiskDecision:
    return PreTradeRiskDecision(
        approved=approved,
        checks=(
            RiskCheck(
                name=RiskCheckName.STRATEGY_SIGNAL,
                passed=approved,
                observed_value="pass" if approved else "fail",
                reason=None if approved else "strategy_signal_rejected",
            ),
        ),
    )


def _execution(
    passed: bool,
    *,
    reasons: tuple[ExecutionGuardReason, ...] = (),
    block_new_entries: bool = False,
    manual_recovery_required: bool = False,
) -> ExecutionGuardDecision:
    return ExecutionGuardDecision(
        passed=passed,
        reasons=reasons,
        block_new_entries=block_new_entries,
        manual_recovery_required=manual_recovery_required,
    )


def _kill_switch(
    active: bool,
    *,
    triggers: tuple[KillSwitchTrigger, ...] = (),
    manual_reset_required: bool = False,
) -> KillSwitchDecision:
    return KillSwitchDecision(
        active=active,
        mode=KillSwitchMode.SIMULATED,
        triggers=triggers,
        block_new_entries=active,
        simulate_cancel_close=active,
        enforce_cancel_close=False,
        manual_reset_required=manual_reset_required,
        reason=None if not triggers else ";".join(trigger.value for trigger in triggers),
    )


def _startup(
    action: StartupRecoveryAction,
    *,
    issue_type: StartupRecoveryIssueType | None = None,
) -> StartupRecoveryDecision:
    issues = (
        (
            StartupRecoveryIssue(
                type=issue_type,
                entity_id="entity_1",
                reason="startup_issue",
            ),
        )
        if issue_type is not None
        else ()
    )
    return StartupRecoveryDecision(
        action=action,
        issues=issues,
        evaluated_at=NOW,
    )
