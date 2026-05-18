"""Strategy input and output models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FeeInputs:
    """Opening and closing fee assumptions in quote currency."""

    spot_open_fee: Decimal
    perp_open_fee: Decimal
    spot_close_fee: Decimal
    perp_close_fee: Decimal

    @property
    def opening_fees(self) -> Decimal:
        return self.spot_open_fee + self.perp_open_fee

    @property
    def closing_fees(self) -> Decimal:
        return self.spot_close_fee + self.perp_close_fee


@dataclass(frozen=True, slots=True)
class SlippageInputs:
    """Entry and exit slippage estimates in quote currency."""

    spot_entry_slippage: Decimal
    perp_entry_slippage: Decimal
    spot_exit_slippage: Decimal
    perp_exit_slippage: Decimal

    @property
    def entry_slippage(self) -> Decimal:
        return self.spot_entry_slippage + self.perp_entry_slippage

    @property
    def exit_slippage(self) -> Decimal:
        return self.spot_exit_slippage + self.perp_exit_slippage


@dataclass(frozen=True, slots=True)
class BufferInputs:
    """Conservative deductions in quote currency."""

    funding_uncertainty_buffer: Decimal
    basis_adverse_move_buffer: Decimal
    residual_delta_buffer: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.funding_uncertainty_buffer
            + self.basis_adverse_move_buffer
            + self.residual_delta_buffer
        )


@dataclass(frozen=True, slots=True)
class FundingArbitrageInputs:
    """Pure strategy inputs for one spot-perp funding opportunity."""

    symbol: str
    proposed_notional_quote: Decimal
    funding_rate: Decimal
    next_funding_time: datetime
    evaluated_at: datetime
    spot_mid: Decimal
    perp_mark: Decimal
    fees: FeeInputs
    slippage: SlippageInputs
    buffers: BufferInputs


@dataclass(frozen=True, slots=True)
class FundingArbitrageThresholds:
    """Strategy-level thresholds before risk engine veto checks."""

    min_net_edge_bps: Decimal
    min_funding_rate_bps: Decimal
    min_seconds_to_funding: int
    max_seconds_to_funding: int
    max_basis_bps: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FundingArbitrageEdge:
    """Detailed edge accounting in quote currency and bps."""

    expected_funding_income: Decimal
    opening_fees: Decimal
    closing_fees: Decimal
    entry_slippage: Decimal
    exit_slippage: Decimal
    funding_uncertainty_buffer: Decimal
    basis_adverse_move_buffer: Decimal
    residual_delta_buffer: Decimal
    net_edge_quote: Decimal
    net_edge_bps: Decimal
    funding_rate_bps: Decimal
    basis_bps: Decimal
    seconds_to_funding: int


@dataclass(frozen=True, slots=True)
class FundingArbitrageSignal:
    """Candidate signal emitted by the strategy layer only."""

    symbol: str
    should_enter: bool
    edge: FundingArbitrageEdge
    reasons: tuple[str, ...]
