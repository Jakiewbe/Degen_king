"""Read-only reporting summaries for risk, opportunity, PnL, reconciliation,
startup recovery, and kill-switch decisions.

Pure functions. No broker calls, no order creation, no exchange access.
Output dicts must not contain order_command, cancel_command, leverage_change,
risk_override, or live_config_mutation fields.
"""

from __future__ import annotations

from decimal import Decimal

from degenking.positions.pnl import PositionPnL
from degenking.reconciliation.service import ReconciliationResult
from degenking.reconciliation.startup_recovery import StartupRecoveryDecision
from degenking.risk.kill_switch import KillSwitchDecision
from degenking.risk.pre_trade import PreTradeRiskDecision
from degenking.strategy.opportunity import OpportunityEvaluation


def _normalize_decimal(value: Decimal) -> str:
    """Strip trailing zeros and decimal point if integer."""
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def summarize_risk_decision(decision: PreTradeRiskDecision) -> dict[str, object]:
    """Summarize a Layer A pre-trade risk decision."""
    failed = [check for check in decision.checks if not check.passed]
    return {
        "approved": decision.approved,
        "failed_checks": tuple(check.name.value for check in failed),
        "rejection_reasons": tuple(
            check.reason or check.name.value for check in failed
        ),
    }


def summarize_opportunity_evaluation(
    evaluation: OpportunityEvaluation,
) -> dict[str, object]:
    """Summarize an opportunity evaluation for reporting."""
    risk_summary = summarize_risk_decision(evaluation.risk_decision)
    return {
        "symbol": evaluation.symbol,
        "should_enter": evaluation.signal.should_enter,
        "risk_approved": evaluation.risk_decision.approved,
        "net_edge_quote": _normalize_decimal(evaluation.signal.edge.net_edge_quote),
        "net_edge_bps": _normalize_decimal(evaluation.signal.edge.net_edge_bps),
        "funding_rate_bps": _normalize_decimal(
            evaluation.signal.edge.funding_rate_bps
        ),
        "reasons": tuple(evaluation.signal.reasons),
        "failed_risk_checks": risk_summary["failed_checks"],
    }


def summarize_position_pnl(pnl: PositionPnL) -> dict[str, object]:
    """Summarize position PnL for reporting."""
    return {
        "symbol": pnl.symbol,
        "total_pnl_quote": _normalize_decimal(pnl.total_pnl_quote),
        "funding_pnl_quote": _normalize_decimal(pnl.funding_pnl_quote),
        "fees_quote": _normalize_decimal(pnl.fees_quote),
        "slippage_quote": _normalize_decimal(pnl.slippage_quote),
        "delta_quantity": _normalize_decimal(pnl.delta_quantity),
        "delta_notional_quote": _normalize_decimal(pnl.delta_notional_quote),
    }


def summarize_reconciliation(result: ReconciliationResult) -> dict[str, object]:
    """Summarize a reconciliation result for reporting."""
    return {
        "symbol": result.symbol,
        "status": result.status.value,
        "discrepancy_count": len(result.discrepancies),
        "discrepancy_types": tuple(
            d.type.value for d in result.discrepancies
        ),
        "manual_recovery_required": result.manual_recovery_required,
    }


def summarize_startup_recovery(
    decision: StartupRecoveryDecision,
) -> dict[str, object]:
    """Summarize a startup recovery decision for reporting."""
    return {
        "action": decision.action.value,
        "new_entries_allowed": decision.new_entries_allowed,
        "manual_recovery_required": decision.manual_recovery_required,
        "issue_count": len(decision.issues),
        "issue_types": tuple(i.type.value for i in decision.issues),
    }


def summarize_kill_switch(decision: KillSwitchDecision) -> dict[str, object]:
    """Summarize a kill-switch decision for reporting."""
    return {
        "active": decision.active,
        "mode": decision.mode.value,
        "triggers": tuple(t.value for t in decision.triggers),
        "block_new_entries": decision.block_new_entries,
        "simulate_cancel_close": decision.simulate_cancel_close,
        "enforce_cancel_close": decision.enforce_cancel_close,
        "manual_reset_required": decision.manual_reset_required,
        "reason": decision.reason,
    }
