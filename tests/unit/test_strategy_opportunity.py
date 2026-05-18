from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.common.enums import MarketType
from degenking.market_data.models import (
    ExchangeStatus,
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)
from degenking.risk.pre_trade import PreTradeRiskLimits, RiskCheckName
from degenking.strategy.models import FundingArbitrageThresholds
from degenking.strategy.opportunity import (
    OpportunityCostConfig,
    OpportunityEvaluationInputs,
    OpportunityFreshnessConfig,
    evaluate_funding_opportunity,
)

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _ticker(market_type: MarketType, *, mark: Decimal | None = None) -> TickerSnapshot:
    return TickerSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=market_type,
        bid=Decimal("100"),
        ask=Decimal("100"),
        mark=mark,
        observed_at=NOW,
    )


def _book(market_type: MarketType) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=market_type,
        bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        asks=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        observed_at=NOW,
    )


def _instrument(market_type: MarketType) -> InstrumentInfo:
    return InstrumentInfo(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=market_type,
        base_asset="BTC",
        quote_asset="USDT",
        price_tick_size=Decimal("0.01"),
        quantity_step_size=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        min_notional=Decimal("10"),
    )


def _inputs(**overrides) -> OpportunityEvaluationInputs:
    base = {
        "symbol": "BTCUSDT",
        "proposed_notional_quote": Decimal("1000"),
        "evaluated_at": NOW,
        "spot_ticker": _ticker(MarketType.SPOT),
        "perp_ticker": _ticker(MarketType.PERPETUAL, mark=Decimal("100")),
        "spot_orderbook": _book(MarketType.SPOT),
        "perp_orderbook": _book(MarketType.PERPETUAL),
        "funding": FundingRateSnapshot(
            exchange="binance",
            symbol="BTCUSDT",
            funding_rate=Decimal("0.003"),
            next_funding_time=NOW + timedelta(hours=2),
            funding_interval_seconds=8 * 3600,
            observed_at=NOW,
        ),
        "spot_instrument": _instrument(MarketType.SPOT),
        "perp_instrument": _instrument(MarketType.PERPETUAL),
        "exchange_status": ExchangeStatus(
            exchange="binance",
            environment="testnet",
            status="ok",
            maintenance=False,
            observed_at=NOW,
        ),
        "latency_ms": 100,
        "max_latency_ms": 750,
        "strategy_thresholds": FundingArbitrageThresholds(
            min_net_edge_bps=Decimal("1"),
            min_funding_rate_bps=Decimal("5"),
            min_seconds_to_funding=900,
            max_seconds_to_funding=25200,
            max_basis_bps=Decimal("75"),
        ),
        "risk_limits": PreTradeRiskLimits(
            max_position_notional_per_symbol=Decimal("5000"),
            max_total_equity_usage_pct=Decimal("50"),
            max_slippage_bps=Decimal("10"),
            min_orderbook_depth_usd=Decimal("1000"),
        ),
        "cost_config": OpportunityCostConfig(
            spot_open_fee_bps=Decimal("1"),
            perp_open_fee_bps=Decimal("1"),
            spot_close_fee_bps=Decimal("1"),
            perp_close_fee_bps=Decimal("1"),
            funding_uncertainty_buffer_pct=Decimal("10"),
            basis_adverse_move_buffer_bps=Decimal("1"),
            residual_delta_buffer_bps=Decimal("1"),
        ),
        "freshness_config": OpportunityFreshnessConfig(
            max_ticker_age_ms=1000,
            max_orderbook_age_ms=1000,
            max_funding_age_ms=60000,
        ),
        "account_equity_quote": Decimal("10000"),
        "available_balance_quote": Decimal("10000"),
    }
    base.update(overrides)
    return OpportunityEvaluationInputs(**base)


def _risk_reason(result, check_name: RiskCheckName) -> str | None:
    return next(
        check.reason
        for check in result.risk_decision.checks
        if check.name == check_name
    )


def test_opportunity_evaluator_approves_clean_candidate() -> None:
    result = evaluate_funding_opportunity(_inputs())

    assert result.signal.should_enter is True
    assert result.risk_decision.approved is True
    assert result.spot_precision.passed is True
    assert result.perp_precision.passed is True
    assert result.strategy_inputs.proposed_notional_quote == Decimal("1000.000")
    assert result.signal.edge.net_edge_quote == Decimal("2.20000")


def test_opportunity_evaluator_rejects_stale_data_via_risk() -> None:
    stale_ticker = TickerSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=Decimal("100"),
        ask=Decimal("100"),
        observed_at=NOW - timedelta(seconds=2),
    )

    result = evaluate_funding_opportunity(_inputs(spot_ticker=stale_ticker))

    assert result.risk_decision.approved is False
    assert _risk_reason(result, RiskCheckName.MARKET_FRESHNESS) == "stale_market_data"


def test_opportunity_evaluator_rejects_precision_failure_via_risk() -> None:
    strict_instrument = InstrumentInfo(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        base_asset="BTC",
        quote_asset="USDT",
        price_tick_size=Decimal("0.01"),
        quantity_step_size=Decimal("0.001"),
        min_quantity=Decimal("100"),
        min_notional=Decimal("100000"),
    )

    result = evaluate_funding_opportunity(_inputs(spot_instrument=strict_instrument))

    assert result.risk_decision.approved is False
    assert _risk_reason(result, RiskCheckName.PRECISION) == "precision_check_failed"


def test_opportunity_evaluator_does_not_create_order_intent() -> None:
    result = evaluate_funding_opportunity(_inputs())

    assert not hasattr(result, "order_intent")
