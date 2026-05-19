from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.common.enums import MarketType, RuntimeMode
from degenking.market_data.models import (
    ExchangeStatus,
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)
from degenking.orders.idempotency import build_client_order_id, build_idempotency_key
from degenking.orders.intents import (
    OrderIntent,
    OrderIntentLeg,
    OrderIntentState,
    OrderSide,
)
from degenking.paper.broker import PaperBroker
from degenking.positions.manager import (
    PositionState,
    apply_fill_to_position,
    new_empty_position,
)
from degenking.positions.pnl import calculate_position_pnl
from degenking.reconciliation.service import ReconciliationStatus, reconcile_paper_state
from degenking.reconciliation.startup_recovery import (
    StartupRecoveryAction,
    evaluate_startup_recovery,
)
from degenking.risk.pre_trade import PreTradeRiskLimits
from degenking.strategy.models import FundingArbitrageThresholds
from degenking.strategy.opportunity import (
    OpportunityCostConfig,
    OpportunityEvaluationInputs,
    OpportunityFreshnessConfig,
    evaluate_funding_opportunity,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_paper_trading_flow_from_opportunity_to_clean_startup_recovery() -> None:
    opportunity_inputs = _opportunity_inputs()
    opportunity = evaluate_funding_opportunity(opportunity_inputs)

    assert opportunity.signal.should_enter is True
    assert opportunity.risk_decision.approved is True

    broker = PaperBroker()
    position = new_empty_position(symbol="BTCUSDT", opened_at=NOW)

    open_spot = _intent(
        intent_id="intent_spot_open",
        leg=OrderIntentLeg.SPOT_OPEN,
        side=OrderSide.BUY,
        quantity=opportunity.spot_precision.rounded_quantity,
        notional_quote=opportunity.spot_precision.notional_quote,
        limit_price=opportunity.spot_precision.rounded_price,
    )
    open_perp = _intent(
        intent_id="intent_perp_open",
        leg=OrderIntentLeg.PERP_OPEN,
        side=OrderSide.SELL,
        quantity=opportunity.perp_precision.rounded_quantity,
        notional_quote=opportunity.perp_precision.notional_quote,
        limit_price=opportunity.perp_precision.rounded_price,
    )

    assert open_spot.idempotency_key
    assert open_perp.idempotency_key
    assert open_spot.idempotency_key != open_perp.idempotency_key

    open_spot_result = broker.submit(
        open_spot,
        opportunity_inputs.spot_orderbook,
        submitted_at=NOW,
        taker_fee_bps=Decimal("1"),
    )
    open_perp_result = broker.submit(
        open_perp,
        opportunity_inputs.perp_orderbook,
        submitted_at=NOW,
        taker_fee_bps=Decimal("1"),
    )

    assert open_spot_result.fill is not None
    assert open_perp_result.fill is not None

    position = apply_fill_to_position(
        position,
        open_spot_result.intent,
        open_spot_result.fill,
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        open_perp_result.intent,
        open_perp_result.fill,
        updated_at=NOW,
    )

    open_pnl = calculate_position_pnl(
        position,
        spot_mid=Decimal("100"),
        perp_mark=Decimal("100"),
    )

    assert position.delta_quantity == Decimal("0.000")
    assert open_pnl.delta_notional_quote == Decimal("0.000")

    close_spot = _intent(
        intent_id="intent_spot_close",
        leg=OrderIntentLeg.SPOT_CLOSE,
        side=OrderSide.SELL,
        quantity=position.spot_quantity,
        notional_quote=position.spot_quantity * Decimal("100"),
        limit_price=Decimal("100"),
    )
    close_perp = _intent(
        intent_id="intent_perp_close",
        leg=OrderIntentLeg.PERP_CLOSE,
        side=OrderSide.BUY,
        quantity=abs(position.perp_quantity),
        notional_quote=abs(position.perp_quantity) * Decimal("100"),
        limit_price=Decimal("100"),
    )

    close_spot_result = broker.submit(
        close_spot,
        opportunity_inputs.spot_orderbook,
        submitted_at=NOW,
        taker_fee_bps=Decimal("1"),
    )
    close_perp_result = broker.submit(
        close_perp,
        opportunity_inputs.perp_orderbook,
        submitted_at=NOW,
        taker_fee_bps=Decimal("1"),
    )

    assert close_spot_result.fill is not None
    assert close_perp_result.fill is not None

    position = apply_fill_to_position(
        position,
        close_spot_result.intent,
        close_spot_result.fill,
        updated_at=NOW,
    )
    position = apply_fill_to_position(
        position,
        close_perp_result.intent,
        close_perp_result.fill,
        updated_at=NOW,
    )

    assert position.state == PositionState.CLOSED
    assert position.is_flat is True

    filled_intents = (
        open_spot_result.intent,
        open_perp_result.intent,
        close_spot_result.intent,
        close_perp_result.intent,
    )
    fills = (
        open_spot_result.fill,
        open_perp_result.fill,
        close_spot_result.fill,
        close_perp_result.fill,
    )
    reconciliation = reconcile_paper_state(
        symbol="BTCUSDT",
        intents=filled_intents,
        fills=fills,
        observed_position=position,
        reconciled_at=NOW,
    )

    assert reconciliation.status == ReconciliationStatus.CLEAN
    assert reconciliation.manual_recovery_required is False

    startup = evaluate_startup_recovery(
        open_intents=(),
        positions=(position,),
        reconciliation_results=(reconciliation,),
        evaluated_at=NOW,
    )

    assert startup.action == StartupRecoveryAction.ALLOW_NEW_ENTRIES
    assert startup.new_entries_allowed is True


def _opportunity_inputs() -> OpportunityEvaluationInputs:
    return OpportunityEvaluationInputs(
        symbol="BTCUSDT",
        proposed_notional_quote=Decimal("1000"),
        evaluated_at=NOW,
        spot_ticker=_ticker(MarketType.SPOT),
        perp_ticker=_ticker(MarketType.PERPETUAL, mark=Decimal("100")),
        spot_orderbook=_book(MarketType.SPOT),
        perp_orderbook=_book(MarketType.PERPETUAL),
        funding=FundingRateSnapshot(
            exchange="binance",
            symbol="BTCUSDT",
            funding_rate=Decimal("0.003"),
            next_funding_time=NOW + timedelta(hours=2),
            funding_interval_seconds=8 * 3600,
            observed_at=NOW,
        ),
        spot_instrument=_instrument(MarketType.SPOT),
        perp_instrument=_instrument(MarketType.PERPETUAL),
        exchange_status=ExchangeStatus(
            exchange="binance",
            environment="testnet",
            status="ok",
            maintenance=False,
            observed_at=NOW,
        ),
        latency_ms=100,
        max_latency_ms=750,
        strategy_thresholds=FundingArbitrageThresholds(
            min_net_edge_bps=Decimal("1"),
            min_funding_rate_bps=Decimal("5"),
            min_seconds_to_funding=900,
            max_seconds_to_funding=25200,
            max_basis_bps=Decimal("75"),
        ),
        risk_limits=PreTradeRiskLimits(
            max_position_notional_per_symbol=Decimal("5000"),
            max_total_equity_usage_pct=Decimal("50"),
            max_slippage_bps=Decimal("10"),
            min_orderbook_depth_usd=Decimal("1000"),
        ),
        cost_config=OpportunityCostConfig(
            spot_open_fee_bps=Decimal("1"),
            perp_open_fee_bps=Decimal("1"),
            spot_close_fee_bps=Decimal("1"),
            perp_close_fee_bps=Decimal("1"),
            funding_uncertainty_buffer_pct=Decimal("10"),
            basis_adverse_move_buffer_bps=Decimal("1"),
            residual_delta_buffer_bps=Decimal("1"),
        ),
        freshness_config=OpportunityFreshnessConfig(
            max_ticker_age_ms=1000,
            max_orderbook_age_ms=1000,
            max_funding_age_ms=60000,
        ),
        account_equity_quote=Decimal("10000"),
        available_balance_quote=Decimal("10000"),
    )


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


def _intent(
    *,
    intent_id: str,
    leg: OrderIntentLeg,
    side: OrderSide,
    quantity: Decimal,
    notional_quote: Decimal,
    limit_price: Decimal,
) -> OrderIntent:
    idempotency_key = build_idempotency_key(
        mode=RuntimeMode.PAPER,
        strategy_id="funding_v1",
        symbol="BTCUSDT",
        leg=leg,
        side=side,
        logical_action_id=intent_id,
    )
    return OrderIntent(
        intent_id=intent_id,
        trace_id="trace_1",
        run_id="run_1",
        strategy_id="funding_v1",
        config_hash="config_hash",
        idempotency_key=idempotency_key,
        symbol="BTCUSDT",
        leg=leg,
        side=side,
        quantity=quantity,
        notional_quote=notional_quote,
        limit_price=limit_price,
        client_order_id=build_client_order_id(
            mode=RuntimeMode.PAPER,
            strategy_id="funding_v1",
            symbol="BTCUSDT",
            leg=leg,
            idempotency_key=idempotency_key,
        ),
        created_at=NOW,
        updated_at=NOW,
        state=OrderIntentState.RISK_APPROVED,
    )
