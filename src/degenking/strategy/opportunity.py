"""Read-only funding opportunity evaluator.

This module stitches together deterministic market-data, cost, strategy, and
pre-trade risk helpers. It does not create order intents and does not place
orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from degenking.market_data.depth import (
    BookSide,
    SlippageEstimate,
    estimate_slippage_for_notional,
)
from degenking.market_data.freshness import FreshnessResult, check_freshness
from degenking.market_data.latency import LatencyCheck, check_latency
from degenking.market_data.models import (
    ExchangeStatus,
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookSnapshot,
    PrecisionCheckResult,
    TickerSnapshot,
)
from degenking.market_data.precision import validate_order_size
from degenking.risk.pre_trade import (
    PreTradeRiskDecision,
    PreTradeRiskInputs,
    PreTradeRiskLimits,
    evaluate_pre_trade,
)
from degenking.strategy.costs import (
    basis_adverse_move_buffer,
    build_buffer_inputs,
    funding_uncertainty_buffer,
    residual_delta_buffer,
    round_trip_fees,
)
from degenking.strategy.funding_arbitrage import evaluate_entry_candidate
from degenking.strategy.models import (
    FundingArbitrageInputs,
    FundingArbitrageSignal,
    FundingArbitrageThresholds,
    SlippageInputs,
)


@dataclass(frozen=True, slots=True)
class OpportunityCostConfig:
    """Cost and buffer assumptions used to build strategy inputs."""

    spot_open_fee_bps: Decimal
    perp_open_fee_bps: Decimal
    spot_close_fee_bps: Decimal
    perp_close_fee_bps: Decimal
    funding_uncertainty_buffer_pct: Decimal
    basis_adverse_move_buffer_bps: Decimal
    residual_delta_buffer_bps: Decimal


@dataclass(frozen=True, slots=True)
class OpportunityFreshnessConfig:
    """Freshness limits for the data needed by one opportunity evaluation."""

    max_ticker_age_ms: int
    max_orderbook_age_ms: int
    max_funding_age_ms: int


@dataclass(frozen=True, slots=True)
class OpportunityEvaluationInputs:
    """All inputs required to evaluate one read-only opportunity."""

    symbol: str
    proposed_notional_quote: Decimal
    evaluated_at: datetime
    spot_ticker: TickerSnapshot
    perp_ticker: TickerSnapshot
    spot_orderbook: OrderBookSnapshot
    perp_orderbook: OrderBookSnapshot
    funding: FundingRateSnapshot
    spot_instrument: InstrumentInfo
    perp_instrument: InstrumentInfo
    exchange_status: ExchangeStatus
    latency_ms: int
    max_latency_ms: int
    strategy_thresholds: FundingArbitrageThresholds
    risk_limits: PreTradeRiskLimits
    cost_config: OpportunityCostConfig
    freshness_config: OpportunityFreshnessConfig
    account_equity_quote: Decimal
    available_balance_quote: Decimal
    current_symbol_notional_quote: Decimal = Decimal("0")
    current_total_used_equity_quote: Decimal = Decimal("0")
    kill_switch_active: bool = False
    manual_recovery_lock: bool = False


@dataclass(frozen=True, slots=True)
class OpportunityEvaluation:
    """Read-only opportunity evaluation result."""

    symbol: str
    signal: FundingArbitrageSignal
    risk_decision: PreTradeRiskDecision
    strategy_inputs: FundingArbitrageInputs
    spot_precision: PrecisionCheckResult
    perp_precision: PrecisionCheckResult
    entry_spot_slippage: SlippageEstimate
    entry_perp_slippage: SlippageEstimate
    exit_spot_slippage: SlippageEstimate
    exit_perp_slippage: SlippageEstimate
    freshness: tuple[FreshnessResult, ...]
    latency: LatencyCheck


def evaluate_funding_opportunity(
    inputs: OpportunityEvaluationInputs,
) -> OpportunityEvaluation:
    """Evaluate a spot-long/perp-short funding candidate without side effects."""

    spot_quantity = inputs.proposed_notional_quote / inputs.spot_ticker.ask
    perp_quantity = inputs.proposed_notional_quote / inputs.perp_ticker.mark_or_mid
    spot_precision = validate_order_size(
        inputs.spot_ticker.ask,
        spot_quantity,
        inputs.spot_instrument,
    )
    perp_precision = validate_order_size(
        inputs.perp_ticker.mark_or_mid,
        perp_quantity,
        inputs.perp_instrument,
    )

    entry_spot_slippage = estimate_slippage_for_notional(
        inputs.spot_orderbook,
        side=BookSide.BUY,
        notional_quote=inputs.proposed_notional_quote,
        reference_price=inputs.spot_ticker.mid,
    )
    entry_perp_slippage = estimate_slippage_for_notional(
        inputs.perp_orderbook,
        side=BookSide.SELL,
        notional_quote=inputs.proposed_notional_quote,
        reference_price=inputs.perp_ticker.mark_or_mid,
    )
    exit_spot_slippage = estimate_slippage_for_notional(
        inputs.spot_orderbook,
        side=BookSide.SELL,
        notional_quote=inputs.proposed_notional_quote,
        reference_price=inputs.spot_ticker.mid,
    )
    exit_perp_slippage = estimate_slippage_for_notional(
        inputs.perp_orderbook,
        side=BookSide.BUY,
        notional_quote=inputs.proposed_notional_quote,
        reference_price=inputs.perp_ticker.mark_or_mid,
    )

    hedge_notional = _hedge_notional(
        inputs.proposed_notional_quote,
        spot_precision,
        perp_precision,
    )
    expected_funding_income = hedge_notional * inputs.funding.funding_rate
    residual_notional = abs(spot_precision.notional_quote - perp_precision.notional_quote)
    fees = round_trip_fees(
        spot_notional_quote=spot_precision.notional_quote,
        perp_notional_quote=perp_precision.notional_quote,
        spot_open_fee_bps=inputs.cost_config.spot_open_fee_bps,
        perp_open_fee_bps=inputs.cost_config.perp_open_fee_bps,
        spot_close_fee_bps=inputs.cost_config.spot_close_fee_bps,
        perp_close_fee_bps=inputs.cost_config.perp_close_fee_bps,
    )
    buffers = build_buffer_inputs(
        funding_uncertainty=funding_uncertainty_buffer(
            expected_funding_income,
            inputs.cost_config.funding_uncertainty_buffer_pct,
        ),
        basis_adverse_move=basis_adverse_move_buffer(
            hedge_notional,
            inputs.cost_config.basis_adverse_move_buffer_bps,
        ),
        residual_delta=residual_delta_buffer(
            residual_notional,
            inputs.cost_config.residual_delta_buffer_bps,
        ),
    )
    strategy_inputs = FundingArbitrageInputs(
        symbol=inputs.symbol,
        proposed_notional_quote=hedge_notional,
        funding_rate=inputs.funding.funding_rate,
        next_funding_time=inputs.funding.next_funding_time,
        evaluated_at=inputs.evaluated_at,
        spot_mid=inputs.spot_ticker.mid,
        perp_mark=inputs.perp_ticker.mark_or_mid,
        fees=fees,
        slippage=SlippageInputs(
            spot_entry_slippage=entry_spot_slippage.slippage_quote,
            perp_entry_slippage=entry_perp_slippage.slippage_quote,
            spot_exit_slippage=exit_spot_slippage.slippage_quote,
            perp_exit_slippage=exit_perp_slippage.slippage_quote,
        ),
        buffers=buffers,
    )
    signal = evaluate_entry_candidate(strategy_inputs, inputs.strategy_thresholds)
    freshness = _freshness_results(inputs)
    latency = check_latency(inputs.latency_ms, max_latency_ms=inputs.max_latency_ms)
    risk_decision = evaluate_pre_trade(
        PreTradeRiskInputs(
            signal=signal,
            limits=inputs.risk_limits,
            freshness=freshness,
            latency=latency,
            entry_slippage_estimates=(entry_spot_slippage, entry_perp_slippage),
            precision_checks=(spot_precision, perp_precision),
            exchange_status=inputs.exchange_status,
            proposed_notional_quote=hedge_notional,
            account_equity_quote=inputs.account_equity_quote,
            available_balance_quote=inputs.available_balance_quote,
            current_symbol_notional_quote=inputs.current_symbol_notional_quote,
            current_total_used_equity_quote=inputs.current_total_used_equity_quote,
            kill_switch_active=inputs.kill_switch_active,
            manual_recovery_lock=inputs.manual_recovery_lock,
        )
    )

    return OpportunityEvaluation(
        symbol=inputs.symbol,
        signal=signal,
        risk_decision=risk_decision,
        strategy_inputs=strategy_inputs,
        spot_precision=spot_precision,
        perp_precision=perp_precision,
        entry_spot_slippage=entry_spot_slippage,
        entry_perp_slippage=entry_perp_slippage,
        exit_spot_slippage=exit_spot_slippage,
        exit_perp_slippage=exit_perp_slippage,
        freshness=freshness,
        latency=latency,
    )


def _hedge_notional(
    proposed_notional: Decimal,
    spot_precision: PrecisionCheckResult,
    perp_precision: PrecisionCheckResult,
) -> Decimal:
    hedge_notional = min(
        proposed_notional,
        spot_precision.notional_quote,
        perp_precision.notional_quote,
    )
    if hedge_notional <= 0:
        return proposed_notional
    return hedge_notional


def _freshness_results(
    inputs: OpportunityEvaluationInputs,
) -> tuple[FreshnessResult, ...]:
    return (
        check_freshness(
            inputs.spot_ticker.observed_at,
            max_age_ms=inputs.freshness_config.max_ticker_age_ms,
            now=inputs.evaluated_at,
        ),
        check_freshness(
            inputs.perp_ticker.observed_at,
            max_age_ms=inputs.freshness_config.max_ticker_age_ms,
            now=inputs.evaluated_at,
        ),
        check_freshness(
            inputs.spot_orderbook.observed_at,
            max_age_ms=inputs.freshness_config.max_orderbook_age_ms,
            now=inputs.evaluated_at,
        ),
        check_freshness(
            inputs.perp_orderbook.observed_at,
            max_age_ms=inputs.freshness_config.max_orderbook_age_ms,
            now=inputs.evaluated_at,
        ),
        check_freshness(
            inputs.funding.observed_at,
            max_age_ms=inputs.freshness_config.max_funding_age_ms,
            now=inputs.evaluated_at,
        ),
    )
