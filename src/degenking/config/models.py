"""Runtime configuration models.

The MVP allows monitor and paper modes only. These models intentionally reject
live execution settings and require the structured kill-switch block.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from degenking.common.enums import (
    ExchangeEnvironment,
    ExchangeName,
    KillSwitchMode,
    RuntimeMode,
)

MVP_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})


class StrictModel(BaseModel):
    """Base config model with immutable, explicit fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExchangeConfig(StrictModel):
    name: ExchangeName
    environment: ExchangeEnvironment
    readonly: bool = True

    @model_validator(mode="after")
    def validate_mvp_exchange(self) -> ExchangeConfig:
        if self.name != ExchangeName.BYBIT:
            raise ValueError("MVP supports only the bybit exchange target")
        if not self.readonly:
            raise ValueError("MVP exchange config must be readonly")
        return self


class MarketDataConfig(StrictModel):
    max_tick_age_ms: PositiveInt
    max_orderbook_age_ms: PositiveInt
    max_funding_age_ms: PositiveInt
    max_latency_ms: PositiveInt


class FundingArbitrageConfig(StrictModel):
    enabled: bool = True
    min_net_edge_bps: float = Field(gt=0)
    min_funding_rate_bps: float = Field(gt=0)
    min_seconds_to_funding: PositiveInt
    max_seconds_to_funding: PositiveInt
    max_basis_bps: float | None = Field(default=None, gt=0)
    max_holding_hours: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_funding_window(self) -> FundingArbitrageConfig:
        if self.min_seconds_to_funding >= self.max_seconds_to_funding:
            raise ValueError("min_seconds_to_funding must be below max_seconds_to_funding")
        return self


class StrategyConfig(StrictModel):
    funding_arbitrage: FundingArbitrageConfig


class RiskConfig(StrictModel):
    max_total_equity_usage_pct: float = Field(gt=0, le=100)
    max_position_notional_per_symbol: float = Field(gt=0)
    max_leverage: float = Field(gt=0, le=1)
    min_liquidation_buffer_pct: float = Field(gt=0)
    max_daily_loss_pct: float = Field(gt=0, le=100)
    max_single_trade_loss_pct: float = Field(gt=0, le=100)
    max_unhedged_seconds: PositiveInt
    max_slippage_bps: float = Field(gt=0)
    min_orderbook_depth_usd: float = Field(gt=0)
    max_api_latency_ms: PositiveInt


class PaperConfig(StrictModel):
    starting_equity_usdt: float = Field(gt=0)
    taker_fee_bps: float = Field(ge=0)
    maker_fee_bps: float = Field(ge=0)
    partial_fill_enabled: bool
    latency_ms: int = Field(ge=0)


class KillSwitchConfig(StrictModel):
    enabled: Literal[True]
    mode: KillSwitchMode
    require_manual_reset: Literal[True]

    @field_validator("mode")
    @classmethod
    def validate_simulated_mode(cls, value: KillSwitchMode) -> KillSwitchMode:
        if value != KillSwitchMode.SIMULATED:
            raise ValueError("monitor and paper modes require simulated kill switch")
        return value


class AgentConfig(StrictModel):
    enabled: bool
    read_sources: tuple[str, ...]
    can_modify_config: Literal[False]
    can_access_execution: Literal[False]


class PersistenceConfig(StrictModel):
    backend: Literal["postgresql"]


class LoggingConfig(StrictModel):
    level: str = "INFO"
    format: Literal["json", "text"] = "json"


class RuntimeConfig(StrictModel):
    mode: RuntimeMode
    exchange: ExchangeConfig
    symbols: tuple[str, ...]
    market_data: MarketDataConfig
    strategy: StrategyConfig
    kill_switch: KillSwitchConfig
    agent: AgentConfig
    persistence: PersistenceConfig
    logging: LoggingConfig
    risk: RiskConfig | None = None
    paper: PaperConfig | None = None
    config_hash: str | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        if not symbols:
            raise ValueError("at least one symbol is required")
        unsupported = set(symbols) - MVP_SYMBOLS
        if unsupported:
            raise ValueError(f"unsupported MVP symbols: {sorted(unsupported)}")
        return symbols

    @model_validator(mode="after")
    def validate_mode_specific_blocks(self) -> RuntimeConfig:
        if self.mode == RuntimeMode.MONITOR and self.paper is not None:
            raise ValueError("monitor mode must not include paper settings")
        if self.mode == RuntimeMode.PAPER:
            if self.paper is None:
                raise ValueError("paper mode requires paper settings")
            if self.risk is None:
                raise ValueError("paper mode requires risk settings")
        return self
