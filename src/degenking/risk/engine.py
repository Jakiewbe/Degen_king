"""Risk engine aggregation entry points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from degenking.reconciliation.startup_recovery import StartupRecoveryDecision
from degenking.risk.execution_guards import (
    ExecutionGuardDecision,
    ExecutionGuardInputs,
    evaluate_execution_guards,
)
from degenking.risk.kill_switch import (
    KillSwitchDecision,
    KillSwitchInputs,
    evaluate_kill_switch,
)
from degenking.risk.pre_trade import (
    PreTradeRiskDecision,
    PreTradeRiskInputs,
    evaluate_pre_trade,
)


class RiskEngineReason(StrEnum):
    """High-level reasons a unified risk decision blocked progress."""

    PRE_TRADE_REJECTED = "pre_trade_rejected"
    EXECUTION_GUARD_BLOCK = "execution_guard_block"
    EXECUTION_MANUAL_RECOVERY = "execution_manual_recovery"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    KILL_SWITCH_MANUAL_RESET = "kill_switch_manual_reset"
    STARTUP_BLOCKED = "startup_blocked"
    STARTUP_MANUAL_RECOVERY = "startup_manual_recovery"


@dataclass(frozen=True, slots=True)
class RiskEngineDecision:
    """Unified risk state consumed by orchestration code."""

    allow_new_entry: bool
    block_symbol: bool
    block_global: bool
    manual_recovery_required: bool
    reasons: tuple[RiskEngineReason, ...]
    source_reasons: tuple[str, ...]
    pre_trade_approved: bool | None = None
    execution_passed: bool | None = None
    kill_switch_active: bool | None = None
    startup_new_entries_allowed: bool | None = None


def aggregate_risk_decisions(
    *,
    pre_trade: PreTradeRiskDecision | None = None,
    execution: ExecutionGuardDecision | None = None,
    kill_switch: KillSwitchDecision | None = None,
    startup: StartupRecoveryDecision | None = None,
) -> RiskEngineDecision:
    """Aggregate Layer A/B/D/startup decisions without side effects."""

    reasons: list[RiskEngineReason] = []
    source_reasons: list[str] = []
    block_symbol = False
    block_global = False
    manual_recovery_required = False

    if pre_trade is not None and not pre_trade.approved:
        block_symbol = True
        reasons.append(RiskEngineReason.PRE_TRADE_REJECTED)
        source_reasons.extend(pre_trade.rejection_reasons)

    if execution is not None and not execution.passed:
        if execution.block_new_entries:
            block_symbol = True
            reasons.append(RiskEngineReason.EXECUTION_GUARD_BLOCK)
        if execution.manual_recovery_required:
            block_symbol = True
            manual_recovery_required = True
            reasons.append(RiskEngineReason.EXECUTION_MANUAL_RECOVERY)
        source_reasons.extend(reason.value for reason in execution.reasons)

    if kill_switch is not None and kill_switch.active:
        block_global = True
        reasons.append(RiskEngineReason.KILL_SWITCH_ACTIVE)
        source_reasons.extend(trigger.value for trigger in kill_switch.triggers)
        if kill_switch.manual_reset_required:
            manual_recovery_required = True
            reasons.append(RiskEngineReason.KILL_SWITCH_MANUAL_RESET)

    if startup is not None and not startup.new_entries_allowed:
        if startup.manual_recovery_required:
            block_global = True
            manual_recovery_required = True
            reasons.append(RiskEngineReason.STARTUP_MANUAL_RECOVERY)
        else:
            block_symbol = True
            reasons.append(RiskEngineReason.STARTUP_BLOCKED)
        source_reasons.extend(issue.reason for issue in startup.issues)

    reasons_tuple = _dedupe_reasons(tuple(reasons))
    source_reasons_tuple = _dedupe_strings(tuple(source_reasons))
    return RiskEngineDecision(
        allow_new_entry=not (block_symbol or block_global or manual_recovery_required),
        block_symbol=block_symbol,
        block_global=block_global,
        manual_recovery_required=manual_recovery_required,
        reasons=reasons_tuple,
        source_reasons=source_reasons_tuple,
        pre_trade_approved=None if pre_trade is None else pre_trade.approved,
        execution_passed=None if execution is None else execution.passed,
        kill_switch_active=None if kill_switch is None else kill_switch.active,
        startup_new_entries_allowed=(
            None if startup is None else startup.new_entries_allowed
        ),
    )


class RiskEngine:
    """Deterministic risk engine facade."""

    def evaluate_pre_trade(self, inputs: PreTradeRiskInputs) -> PreTradeRiskDecision:
        """Run Layer A pre-trade veto checks."""

        return evaluate_pre_trade(inputs)

    def evaluate_execution_guards(
        self,
        inputs: ExecutionGuardInputs,
    ) -> ExecutionGuardDecision:
        """Run Layer B in-flight execution guards."""

        return evaluate_execution_guards(inputs)

    def evaluate_kill_switch(self, inputs: KillSwitchInputs) -> KillSwitchDecision:
        """Run Layer D global kill-switch evaluation."""

        return evaluate_kill_switch(inputs)

    def aggregate(
        self,
        *,
        pre_trade: PreTradeRiskDecision | None = None,
        execution: ExecutionGuardDecision | None = None,
        kill_switch: KillSwitchDecision | None = None,
        startup: StartupRecoveryDecision | None = None,
    ) -> RiskEngineDecision:
        """Aggregate existing risk-layer decisions into one view."""

        return aggregate_risk_decisions(
            pre_trade=pre_trade,
            execution=execution,
            kill_switch=kill_switch,
            startup=startup,
        )


def _dedupe_reasons(
    reasons: tuple[RiskEngineReason, ...],
) -> tuple[RiskEngineReason, ...]:
    seen: set[RiskEngineReason] = set()
    deduped: list[RiskEngineReason] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return tuple(deduped)


def _dedupe_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return tuple(deduped)
