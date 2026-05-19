from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.audit.events import AuditEventType
from degenking.common.enums import MarketType
from degenking.market_data.models import (
    ExchangeStatus,
    FundingRateSnapshot,
    InstrumentInfo,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)
from degenking.orders.intents import OrderIntentState
from degenking.paper.orchestrator import (
    PaperEntryRunInputs,
    execute_paper_entry_run,
)
from degenking.reconciliation.service import ReconciliationStatus
from degenking.risk.pre_trade import PreTradeRiskLimits
from degenking.strategy.models import FundingArbitrageThresholds
from degenking.strategy.opportunity import (
    OpportunityCostConfig,
    OpportunityEvaluationInputs,
    OpportunityFreshnessConfig,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_execute_paper_entry_run_approved_flow() -> None:
    result = execute_paper_entry_run(_run_inputs())

    assert result.opportunity.signal.should_enter is True
    assert result.risk_decision.allow_new_entry is True
    assert len(result.intents) == 2
    assert len(result.fills) == 2
    assert {intent.state for intent in result.intents} == {OrderIntentState.FILLED}
    assert all(intent.idempotency_key for intent in result.intents)
    assert result.intents[0].idempotency_key != result.intents[1].idempotency_key
    assert result.position.spot_quantity == Decimal("10.000")
    assert result.position.perp_quantity == Decimal("-10.000")
    assert result.position.delta_quantity == Decimal("0.000")
    assert result.pnl is not None
    assert result.pnl.delta_notional_quote == Decimal("0.000")
    assert result.reconciliation is not None
    assert result.reconciliation.status == ReconciliationStatus.CLEAN
    assert result.reconciliation.manual_recovery_required is False
    assert _event_types(result) == (
        AuditEventType.PRE_TRADE_RISK_DECIDED.value,
        AuditEventType.RISK_ENGINE_DECIDED.value,
        AuditEventType.ORDER_INTENT_UPDATED.value,
        AuditEventType.ORDER_INTENT_UPDATED.value,
        AuditEventType.PAPER_FILL_RECORDED.value,
        AuditEventType.PAPER_FILL_RECORDED.value,
        AuditEventType.POSITION_UPDATED.value,
        AuditEventType.PNL_RECORDED.value,
        AuditEventType.RECONCILIATION_COMPLETED.value,
    )


def test_execute_paper_entry_run_rejected_flow_creates_no_intents() -> None:
    result = execute_paper_entry_run(
        _run_inputs(
            opportunity_inputs=_opportunity_inputs(manual_recovery_lock=True),
        )
    )

    assert result.opportunity.risk_decision.approved is False
    assert result.risk_decision.allow_new_entry is False
    assert result.risk_decision.block_symbol is True
    assert result.intents == ()
    assert result.fills == ()
    assert result.pnl is None
    assert result.reconciliation is None
    assert result.position.is_flat is True
    assert _event_types(result) == (
        AuditEventType.PRE_TRADE_RISK_DECIDED.value,
        AuditEventType.RISK_ENGINE_DECIDED.value,
    )


def test_execute_paper_entry_run_partial_fill_reconciles_clean_partial_position() -> None:
    result = execute_paper_entry_run(_run_inputs(fill_ratio=Decimal("0.25")))

    assert len(result.fills) == 2
    assert {intent.state for intent in result.intents} == {
        OrderIntentState.PARTIALLY_FILLED
    }
    assert result.position.spot_quantity == Decimal("2.50000")
    assert result.position.perp_quantity == Decimal("-2.50000")
    assert result.reconciliation is not None
    assert result.reconciliation.status == ReconciliationStatus.CLEAN


def _event_types(result) -> tuple[str, ...]:
    return tuple(event.event_type for event in result.audit_events)


def _run_inputs(
    *,
    opportunity_inputs: OpportunityEvaluationInputs | None = None,
    fill_ratio: Decimal = Decimal("1"),
) -> PaperEntryRunInputs:
    return PaperEntryRunInputs(
        opportunity_inputs=opportunity_inputs or _opportunity_inputs(),
        trace_id="trace_1",
        run_id="run_1",
        strategy_id="funding_v1",
        config_hash="config_hash",
        submitted_at=NOW,
        spot_taker_fee_bps=Decimal("1"),
        perp_taker_fee_bps=Decimal("1"),
        fill_ratio=fill_ratio,
    )


def _opportunity_inputs(**overrides) -> OpportunityEvaluationInputs:
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
