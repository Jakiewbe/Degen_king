"""Synthetic paper-run fixtures for CLI dry runs.

These helpers create deterministic local market snapshots. They do not connect
to Binance and do not read account credentials.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from degenking.common.enums import MarketType
from degenking.config.models import RuntimeConfig
from degenking.market_data.models import (
    ExchangeStatus,
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)
from degenking.risk.pre_trade import PreTradeRiskLimits
from degenking.strategy.models import FundingArbitrageThresholds
from degenking.strategy.opportunity import (
    OpportunityCostConfig,
    OpportunityEvaluationInputs,
    OpportunityFreshnessConfig,
)


def build_synthetic_opportunity_inputs(
    config: RuntimeConfig,
    *,
    symbol: str,
    proposed_notional_quote: Decimal,
    evaluated_at: datetime,
) -> OpportunityEvaluationInputs:
    """Build deterministic local inputs for a paper dry run."""

    if config.paper is None or config.risk is None:
        raise ValueError("paper dry run requires paper and risk config blocks")
    if symbol not in config.symbols:
        raise ValueError(f"symbol {symbol} is not configured")

    return OpportunityEvaluationInputs(
        symbol=symbol,
        proposed_notional_quote=proposed_notional_quote,
        evaluated_at=evaluated_at,
        spot_ticker=_ticker(symbol, MarketType.SPOT, evaluated_at),
        perp_ticker=_ticker(
            symbol,
            MarketType.PERPETUAL,
            evaluated_at,
            mark=Decimal("100"),
        ),
        spot_orderbook=_book(symbol, MarketType.SPOT, evaluated_at),
        perp_orderbook=_book(symbol, MarketType.PERPETUAL, evaluated_at),
        funding=FundingRateSnapshot(
            exchange=config.exchange.name.value,
            symbol=symbol,
            funding_rate=_bps_to_rate(
                Decimal(str(config.strategy.funding_arbitrage.min_funding_rate_bps))
                + Decimal("25")
            ),
            next_funding_time=evaluated_at + timedelta(hours=2),
            funding_interval_seconds=8 * 3600,
            observed_at=evaluated_at,
        ),
        spot_instrument=_instrument(symbol, MarketType.SPOT),
        perp_instrument=_instrument(symbol, MarketType.PERPETUAL),
        exchange_status=ExchangeStatus(
            exchange=config.exchange.name.value,
            environment=config.exchange.environment.value,
            status="ok",
            maintenance=False,
            observed_at=evaluated_at,
        ),
        latency_ms=config.paper.latency_ms,
        max_latency_ms=config.market_data.max_latency_ms,
        strategy_thresholds=FundingArbitrageThresholds(
            min_net_edge_bps=Decimal(str(config.strategy.funding_arbitrage.min_net_edge_bps)),
            min_funding_rate_bps=Decimal(
                str(config.strategy.funding_arbitrage.min_funding_rate_bps)
            ),
            min_seconds_to_funding=config.strategy.funding_arbitrage.min_seconds_to_funding,
            max_seconds_to_funding=config.strategy.funding_arbitrage.max_seconds_to_funding,
            max_basis_bps=Decimal(
                str(config.strategy.funding_arbitrage.max_basis_bps or "0")
            ),
        ),
        risk_limits=PreTradeRiskLimits(
            max_position_notional_per_symbol=Decimal(
                str(config.risk.max_position_notional_per_symbol)
            ),
            max_total_equity_usage_pct=Decimal(str(config.risk.max_total_equity_usage_pct)),
            max_slippage_bps=Decimal(str(config.risk.max_slippage_bps)),
            min_orderbook_depth_usd=Decimal(str(config.risk.min_orderbook_depth_usd)),
        ),
        cost_config=OpportunityCostConfig(
            spot_open_fee_bps=Decimal(str(config.paper.maker_fee_bps)),
            perp_open_fee_bps=Decimal(str(config.paper.maker_fee_bps)),
            spot_close_fee_bps=Decimal(str(config.paper.maker_fee_bps)),
            perp_close_fee_bps=Decimal(str(config.paper.maker_fee_bps)),
            funding_uncertainty_buffer_pct=Decimal("10"),
            basis_adverse_move_buffer_bps=Decimal("1"),
            residual_delta_buffer_bps=Decimal("1"),
        ),
        freshness_config=OpportunityFreshnessConfig(
            max_ticker_age_ms=config.market_data.max_tick_age_ms,
            max_orderbook_age_ms=config.market_data.max_orderbook_age_ms,
            max_funding_age_ms=config.market_data.max_funding_age_ms,
        ),
        account_equity_quote=Decimal(str(config.paper.starting_equity_usdt)),
        available_balance_quote=Decimal(str(config.paper.starting_equity_usdt)),
    )


def _ticker(
    symbol: str,
    market_type: MarketType,
    observed_at: datetime,
    *,
    mark: Decimal | None = None,
) -> TickerSnapshot:
    return TickerSnapshot(
        exchange="binance",
        symbol=symbol,
        market_type=market_type,
        bid=Decimal("100"),
        ask=Decimal("100"),
        mark=mark,
        observed_at=observed_at,
    )


def _book(
    symbol: str,
    market_type: MarketType,
    observed_at: datetime,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol=symbol,
        market_type=market_type,
        bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        asks=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        observed_at=observed_at,
    )


def _instrument(symbol: str, market_type: MarketType) -> InstrumentInfo:
    return InstrumentInfo(
        exchange="binance",
        symbol=symbol,
        market_type=market_type,
        base_asset=symbol.removesuffix("USDT"),
        quote_asset="USDT",
        price_tick_size=Decimal("0.01"),
        quantity_step_size=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        min_notional=Decimal("10"),
    )


def _bps_to_rate(value: Decimal) -> Decimal:
    return value / Decimal("10000")
