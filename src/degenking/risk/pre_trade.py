"""Layer A pre-trade veto checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from degenking.market_data.depth import SlippageEstimate
from degenking.market_data.freshness import FreshnessResult
from degenking.market_data.latency import LatencyCheck
from degenking.market_data.models import ExchangeStatus, PrecisionCheckResult
from degenking.strategy.models import FundingArbitrageSignal


class RiskCheckName(StrEnum):
    """Named pre-trade checks that can map directly to persistence rows."""

    STRATEGY_SIGNAL = "strategy_signal"
    MARKET_FRESHNESS = "market_freshness"
    API_LATENCY = "api_latency"
    EXCHANGE_STATUS = "exchange_status"
    KILL_SWITCH = "kill_switch"
    MANUAL_RECOVERY_LOCK = "manual_recovery_lock"
    ORDERBOOK_DEPTH = "orderbook_depth"
    SLIPPAGE = "slippage"
    PRECISION = "precision"
    SYMBOL_NOTIONAL = "symbol_notional"
    TOTAL_EQUITY_USAGE = "total_equity_usage"
    ACCOUNT_BALANCE = "account_balance"


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """One persisted risk check result."""

    name: RiskCheckName
    passed: bool
    observed_value: str
    limit_value: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PreTradeRiskLimits:
    """Hard pre-trade limits used by Layer A."""

    max_position_notional_per_symbol: Decimal
    max_total_equity_usage_pct: Decimal
    max_slippage_bps: Decimal
    min_orderbook_depth_usd: Decimal
    min_available_balance_quote: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class PreTradeRiskInputs:
    """Inputs required to evaluate one candidate before intent creation."""

    signal: FundingArbitrageSignal
    limits: PreTradeRiskLimits
    freshness: tuple[FreshnessResult, ...]
    latency: LatencyCheck
    entry_slippage_estimates: tuple[SlippageEstimate, ...]
    exchange_status: ExchangeStatus
    proposed_notional_quote: Decimal
    account_equity_quote: Decimal
    available_balance_quote: Decimal
    precision_checks: tuple[PrecisionCheckResult, ...] = ()
    current_symbol_notional_quote: Decimal = Decimal("0")
    current_total_used_equity_quote: Decimal = Decimal("0")
    kill_switch_active: bool = False
    manual_recovery_lock: bool = False


@dataclass(frozen=True, slots=True)
class PreTradeRiskDecision:
    """Layer A approval result."""

    approved: bool
    checks: tuple[RiskCheck, ...]

    @property
    def rejection_reasons(self) -> tuple[str, ...]:
        return tuple(
            check.reason or check.name.value for check in self.checks if not check.passed
        )


def evaluate_pre_trade(inputs: PreTradeRiskInputs) -> PreTradeRiskDecision:
    """Evaluate hard pre-trade veto checks.

    This function is deterministic and side-effect free. It does not create an
    OrderIntent and does not place orders.
    """

    checks = [
        _check_strategy_signal(inputs.signal),
        _check_freshness(inputs.freshness),
        _check_latency(inputs.latency),
        _check_exchange_status(inputs.exchange_status),
        _check_kill_switch(inputs.kill_switch_active),
        _check_manual_recovery_lock(inputs.manual_recovery_lock),
        _check_orderbook_depth(
            inputs.entry_slippage_estimates,
            inputs.limits.min_orderbook_depth_usd,
        ),
        _check_slippage(
            inputs.entry_slippage_estimates,
            inputs.limits.max_slippage_bps,
        ),
        _check_precision(inputs.precision_checks),
        _check_symbol_notional(inputs),
        _check_total_equity_usage(inputs),
        _check_account_balance(inputs),
    ]
    return PreTradeRiskDecision(
        approved=all(check.passed for check in checks),
        checks=tuple(checks),
    )


def _check_strategy_signal(signal: FundingArbitrageSignal) -> RiskCheck:
    return RiskCheck(
        name=RiskCheckName.STRATEGY_SIGNAL,
        passed=signal.should_enter,
        observed_value="pass" if signal.should_enter else ",".join(signal.reasons),
        reason=None if signal.should_enter else "strategy_signal_rejected",
    )


def _check_freshness(results: tuple[FreshnessResult, ...]) -> RiskCheck:
    stale = [result for result in results if not result.is_fresh]
    observed_value = (
        "fresh"
        if not stale
        else ";".join(result.reason or "stale" for result in stale)
    )
    return RiskCheck(
        name=RiskCheckName.MARKET_FRESHNESS,
        passed=not stale,
        observed_value=observed_value,
        reason=None if not stale else "stale_market_data",
    )


def _check_latency(latency: LatencyCheck) -> RiskCheck:
    return RiskCheck(
        name=RiskCheckName.API_LATENCY,
        passed=latency.passed,
        observed_value=str(latency.latency_ms),
        limit_value=str(latency.max_latency_ms),
        reason=None if latency.passed else "api_latency_above_threshold",
    )


def _check_exchange_status(status: ExchangeStatus) -> RiskCheck:
    is_healthy = (
        status.status.lower() in {"ok", "healthy", "normal"} and not status.maintenance
    )
    return RiskCheck(
        name=RiskCheckName.EXCHANGE_STATUS,
        passed=is_healthy,
        observed_value=f"{status.status}:maintenance={status.maintenance}",
        limit_value="ok_or_healthy_or_normal_without_maintenance",
        reason=None if is_healthy else "exchange_status_degraded",
    )


def _check_kill_switch(active: bool) -> RiskCheck:
    return RiskCheck(
        name=RiskCheckName.KILL_SWITCH,
        passed=not active,
        observed_value=str(active).lower(),
        limit_value="false",
        reason=None if not active else "kill_switch_active",
    )


def _check_manual_recovery_lock(active: bool) -> RiskCheck:
    return RiskCheck(
        name=RiskCheckName.MANUAL_RECOVERY_LOCK,
        passed=not active,
        observed_value=str(active).lower(),
        limit_value="false",
        reason=None if not active else "manual_recovery_lock_active",
    )


def _check_orderbook_depth(
    estimates: tuple[SlippageEstimate, ...],
    min_depth: Decimal,
) -> RiskCheck:
    insufficient = [
        estimate for estimate in estimates if estimate.filled_notional_quote < min_depth
    ]
    return RiskCheck(
        name=RiskCheckName.ORDERBOOK_DEPTH,
        passed=not insufficient,
        observed_value=",".join(
            str(estimate.filled_notional_quote) for estimate in estimates
        ),
        limit_value=str(min_depth),
        reason=None if not insufficient else "insufficient_orderbook_depth",
    )


def _check_slippage(
    estimates: tuple[SlippageEstimate, ...],
    max_slippage_bps: Decimal,
) -> RiskCheck:
    bad_estimates = [
        estimate
        for estimate in estimates
        if not estimate.fully_filled or estimate.slippage_bps > max_slippage_bps
    ]
    return RiskCheck(
        name=RiskCheckName.SLIPPAGE,
        passed=not bad_estimates,
        observed_value=",".join(str(estimate.slippage_bps) for estimate in estimates),
        limit_value=str(max_slippage_bps),
        reason=None if not bad_estimates else "slippage_or_fill_depth_exceeds_limit",
    )


def _check_precision(checks: tuple[PrecisionCheckResult, ...]) -> RiskCheck:
    failed = [check for check in checks if not check.passed]
    observed_value = (
        "pass" if not failed else ";".join(check.reason or "failed" for check in failed)
    )
    return RiskCheck(
        name=RiskCheckName.PRECISION,
        passed=not failed,
        observed_value=observed_value,
        reason=None if not failed else "precision_check_failed",
    )


def _check_symbol_notional(inputs: PreTradeRiskInputs) -> RiskCheck:
    next_symbol_notional = (
        inputs.current_symbol_notional_quote + inputs.proposed_notional_quote
    )
    limit = inputs.limits.max_position_notional_per_symbol
    return RiskCheck(
        name=RiskCheckName.SYMBOL_NOTIONAL,
        passed=next_symbol_notional <= limit,
        observed_value=str(next_symbol_notional),
        limit_value=str(limit),
        reason=(
            None
            if next_symbol_notional <= limit
            else "symbol_notional_limit_exceeded"
        ),
    )


def _check_total_equity_usage(inputs: PreTradeRiskInputs) -> RiskCheck:
    if inputs.account_equity_quote <= 0:
        return RiskCheck(
            name=RiskCheckName.TOTAL_EQUITY_USAGE,
            passed=False,
            observed_value=str(inputs.account_equity_quote),
            limit_value="account_equity_quote > 0",
            reason="account_equity_not_positive",
        )

    next_used = inputs.current_total_used_equity_quote + inputs.proposed_notional_quote
    usage_pct = next_used / inputs.account_equity_quote * Decimal("100")
    limit = inputs.limits.max_total_equity_usage_pct
    return RiskCheck(
        name=RiskCheckName.TOTAL_EQUITY_USAGE,
        passed=usage_pct <= limit,
        observed_value=str(usage_pct),
        limit_value=str(limit),
        reason=None if usage_pct <= limit else "total_equity_usage_limit_exceeded",
    )


def _check_account_balance(inputs: PreTradeRiskInputs) -> RiskCheck:
    required = max(inputs.proposed_notional_quote, inputs.limits.min_available_balance_quote)
    passed = inputs.available_balance_quote >= required
    return RiskCheck(
        name=RiskCheckName.ACCOUNT_BALANCE,
        passed=passed,
        observed_value=str(inputs.available_balance_quote),
        limit_value=str(required),
        reason=None if passed else "insufficient_account_balance",
    )
