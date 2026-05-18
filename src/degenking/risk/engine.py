"""Risk engine entry points."""

from __future__ import annotations

from degenking.risk.pre_trade import (
    PreTradeRiskDecision,
    PreTradeRiskInputs,
    evaluate_pre_trade,
)


class RiskEngine:
    """Deterministic risk engine facade."""

    def evaluate_pre_trade(self, inputs: PreTradeRiskInputs) -> PreTradeRiskDecision:
        """Run Layer A pre-trade veto checks."""

        return evaluate_pre_trade(inputs)
