from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from degenking.common.enums import MarketType
from degenking.market_data.depth import BookSide, estimate_slippage_for_notional
from degenking.market_data.freshness import check_freshness
from degenking.market_data.latency import check_latency
from degenking.market_data.models import (
    ExchangeStatus,
    OrderBookLevel,
    OrderBookSnapshot,
)
from degenking.risk.pre_trade import (
    PreTradeRiskInputs,
    PreTradeRiskLimits,
    RiskCheckName,
    evaluate_pre_trade,
)
from degenking.strategy.funding_arbitrage import evaluate_entry_candidate
from degenking.strategy.models import (
    BufferInputs,
    FeeInputs,
    FundingArbitrageInputs,
    FundingArbitrageThresholds,
    SlippageInputs,
)

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        asks=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1000")),),
        observed_at=NOW,
    )


def _signal(should_pass: bool = True):
    funding_rate = Decimal("0.003") if should_pass else Decimal("0.0001")
    inputs = FundingArbitrageInputs(
        symbol="BTCUSDT",
        proposed_notional_quote=Decimal("100"),
        funding_rate=funding_rate,
        next_funding_time=NOW + timedelta(hours=2),
        evaluated_at=NOW,
        spot_mid=Decimal("100"),
        perp_mark=Decimal("100.10"),
        fees=FeeInputs(
            spot_open_fee=Decimal("0"),
            perp_open_fee=Decimal("0"),
            spot_close_fee=Decimal("0"),
            perp_close_fee=Decimal("0"),
        ),
        slippage=SlippageInputs(
            spot_entry_slippage=Decimal("0"),
            perp_entry_slippage=Decimal("0"),
            spot_exit_slippage=Decimal("0"),
            perp_exit_slippage=Decimal("0"),
        ),
        buffers=BufferInputs(
            funding_uncertainty_buffer=Decimal("0"),
            basis_adverse_move_buffer=Decimal("0"),
            residual_delta_buffer=Decimal("0"),
        ),
    )
    thresholds = FundingArbitrageThresholds(
        min_net_edge_bps=Decimal("1"),
        min_funding_rate_bps=Decimal("5"),
        min_seconds_to_funding=900,
        max_seconds_to_funding=25200,
        max_basis_bps=Decimal("75"),
    )
    return evaluate_entry_candidate(inputs, thresholds)


def _limits() -> PreTradeRiskLimits:
    return PreTradeRiskLimits(
        max_position_notional_per_symbol=Decimal("1000"),
        max_total_equity_usage_pct=Decimal("50"),
        max_slippage_bps=Decimal("10"),
        min_orderbook_depth_usd=Decimal("100"),
    )


def _inputs(**overrides) -> PreTradeRiskInputs:
    book = _book()
    base = {
        "signal": _signal(),
        "limits": _limits(),
        "freshness": (check_freshness(NOW, max_age_ms=1000, now=NOW),),
        "latency": check_latency(100, max_latency_ms=750),
        "entry_slippage_estimates": (
            estimate_slippage_for_notional(
                book,
                side=BookSide.BUY,
                notional_quote=Decimal("100"),
                reference_price=Decimal("100"),
            ),
            estimate_slippage_for_notional(
                book,
                side=BookSide.SELL,
                notional_quote=Decimal("100"),
                reference_price=Decimal("100"),
            ),
        ),
        "exchange_status": ExchangeStatus(
            exchange="binance",
            environment="testnet",
            status="ok",
            maintenance=False,
            observed_at=NOW,
        ),
        "proposed_notional_quote": Decimal("100"),
        "account_equity_quote": Decimal("1000"),
        "available_balance_quote": Decimal("1000"),
    }
    base.update(overrides)
    return PreTradeRiskInputs(**base)


def _check(decision, name: RiskCheckName):
    return next(check for check in decision.checks if check.name == name)


def test_pre_trade_approves_clean_candidate() -> None:
    decision = evaluate_pre_trade(_inputs())

    assert decision.approved is True
    assert all(check.passed for check in decision.checks)


def test_pre_trade_rejects_strategy_signal_failure() -> None:
    decision = evaluate_pre_trade(_inputs(signal=_signal(should_pass=False)))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.STRATEGY_SIGNAL).reason == "strategy_signal_rejected"


def test_pre_trade_rejects_stale_market_data() -> None:
    stale = check_freshness(NOW - timedelta(seconds=2), max_age_ms=1000, now=NOW)

    decision = evaluate_pre_trade(_inputs(freshness=(stale,)))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.MARKET_FRESHNESS).reason == "stale_market_data"


def test_pre_trade_rejects_high_latency() -> None:
    decision = evaluate_pre_trade(_inputs(latency=check_latency(751, max_latency_ms=750)))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.API_LATENCY).reason == "api_latency_above_threshold"


def test_pre_trade_rejects_exchange_maintenance() -> None:
    decision = evaluate_pre_trade(
        _inputs(
            exchange_status=ExchangeStatus(
                exchange="binance",
                environment="testnet",
                status="ok",
                maintenance=True,
                observed_at=NOW,
            )
        )
    )

    assert decision.approved is False
    assert _check(decision, RiskCheckName.EXCHANGE_STATUS).reason == "exchange_status_degraded"


def test_pre_trade_rejects_kill_switch_and_manual_recovery_lock() -> None:
    decision = evaluate_pre_trade(_inputs(kill_switch_active=True, manual_recovery_lock=True))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.KILL_SWITCH).reason == "kill_switch_active"
    assert (
        _check(decision, RiskCheckName.MANUAL_RECOVERY_LOCK).reason
        == "manual_recovery_lock_active"
    )


def test_pre_trade_rejects_insufficient_depth() -> None:
    decision = evaluate_pre_trade(
        _inputs(
            limits=PreTradeRiskLimits(
                max_position_notional_per_symbol=Decimal("1000"),
                max_total_equity_usage_pct=Decimal("50"),
                max_slippage_bps=Decimal("10"),
                min_orderbook_depth_usd=Decimal("10000"),
            )
        )
    )

    assert decision.approved is False
    assert _check(decision, RiskCheckName.ORDERBOOK_DEPTH).reason == "insufficient_orderbook_depth"


def test_pre_trade_rejects_unfilled_or_high_slippage_estimate() -> None:
    thin_book = OrderBookSnapshot(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bids=(OrderBookLevel(price=Decimal("90"), quantity=Decimal("1")),),
        asks=(OrderBookLevel(price=Decimal("110"), quantity=Decimal("1")),),
        observed_at=NOW,
    )
    estimate = estimate_slippage_for_notional(
        thin_book,
        side=BookSide.BUY,
        notional_quote=Decimal("100"),
        reference_price=Decimal("100"),
    )

    decision = evaluate_pre_trade(_inputs(entry_slippage_estimates=(estimate,)))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.SLIPPAGE).reason == "slippage_or_fill_depth_exceeds_limit"


def test_pre_trade_rejects_precision_failure() -> None:
    from degenking.market_data.models import PrecisionCheckResult

    decision = evaluate_pre_trade(
        _inputs(
            precision_checks=(
                PrecisionCheckResult(
                    rounded_price=Decimal("100"),
                    rounded_quantity=Decimal("0"),
                    notional_quote=Decimal("0"),
                    min_quantity_ok=False,
                    min_notional_ok=False,
                    passed=False,
                    reason="quantity below minimum",
                ),
            )
        )
    )

    assert decision.approved is False
    assert _check(decision, RiskCheckName.PRECISION).reason == "precision_check_failed"


def test_pre_trade_rejects_symbol_notional_limit() -> None:
    decision = evaluate_pre_trade(_inputs(current_symbol_notional_quote=Decimal("950")))

    assert decision.approved is False
    assert (
        _check(decision, RiskCheckName.SYMBOL_NOTIONAL).reason
        == "symbol_notional_limit_exceeded"
    )


def test_pre_trade_rejects_total_equity_usage_limit() -> None:
    decision = evaluate_pre_trade(_inputs(current_total_used_equity_quote=Decimal("450")))

    assert decision.approved is False
    assert (
        _check(decision, RiskCheckName.TOTAL_EQUITY_USAGE).reason
        == "total_equity_usage_limit_exceeded"
    )


def test_pre_trade_rejects_insufficient_balance() -> None:
    decision = evaluate_pre_trade(_inputs(available_balance_quote=Decimal("99")))

    assert decision.approved is False
    assert _check(decision, RiskCheckName.ACCOUNT_BALANCE).reason == "insufficient_account_balance"


def test_pre_trade_rejects_non_positive_equity() -> None:
    decision = evaluate_pre_trade(_inputs(account_equity_quote=Decimal("0")))

    assert decision.approved is False
    assert (
        _check(decision, RiskCheckName.TOTAL_EQUITY_USAGE).reason
        == "account_equity_not_positive"
    )
