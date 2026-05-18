# Strategy: Spot-Perpetual Funding Arbitrage

## Objective

The initial strategy evaluates whether positive perpetual funding is large enough to justify a delta-neutral paper position:

- Long spot.
- Short perpetual.

The strategy only emits candidate signals. It does not create order intents and cannot place orders.

## Edge Accounting

Compute edge in quote currency first, then expose basis points relative to proposed notional.

```text
net_edge_quote =
  expected_funding_income
  - opening_fees
  - closing_fees
  - entry_slippage
  - exit_slippage
  - funding_uncertainty_buffer
  - basis_adverse_move_buffer
  - residual_delta_buffer

net_edge_bps = net_edge_quote / proposed_notional_quote * 10000
```

## Required Inputs

Market inputs:

- Spot bid, ask, mid.
- Spot order book depth.
- Perp bid, ask, mark, index.
- Perp order book depth.
- Funding rate.
- Next funding time.
- Funding interval.

Instrument inputs:

- Spot minimum notional.
- Perp minimum notional.
- Quantity precision.
- Price tick size.
- Contract size, if applicable.

Cost inputs:

- Spot maker and taker fees.
- Perp maker and taker fees.
- Estimated entry slippage for both legs.
- Estimated exit slippage for both legs.

Account inputs:

- Quote balance.
- Base balance.
- Available margin.
- Existing spot and perpetual exposure.

Risk context:

- Market data freshness.
- API/WebSocket latency.
- Maximum symbol notional.
- Maximum total equity usage.
- Current kill-switch and manual recovery state.

## Entry Conditions

A candidate signal may be emitted only when:

- Funding rate is positive and above `min_funding_rate_bps`.
- Time to funding is within `[min_seconds_to_funding, max_seconds_to_funding]`.
- `net_edge_bps >= min_net_edge_bps`.
- Spot and perp order books support the proposed notional within slippage limits.
- Rounded quantities satisfy minimum notional, precision, and tick-size requirements.
- Account balances can support the spot leg and simulated perp margin.
- Data freshness and latency checks pass.
- There is no unresolved risk incident, manual recovery lock, or active kill switch.

The risk engine still has absolute veto power after the strategy emits a candidate.

## Exit Conditions

Position manager creates an exit candidate when:

- Funding is no longer favorable.
- Net edge after estimated exit costs falls below the configured threshold.
- Basis deterioration exceeds policy.
- Hedge delta exceeds tolerance after rounding, partial fill, or price movement.
- Max holding time is reached.
- Position-level risk guard triggers.
- Manual shutdown or kill-switch simulation triggers.

## Slippage And Buffers

Slippage is estimated by walking order book levels until the proposed notional is filled. The weighted-average execution price is compared with mid price.

Buffers are conservative deductions:

- `funding_uncertainty_buffer`: protects against funding-rate changes before settlement.
- `basis_adverse_move_buffer`: protects against basis moving before entry or before exit.
- `residual_delta_buffer`: protects against imperfect hedging from lot-size rounding or partial fills.

## Monitor Mode

Monitor mode may compute and persist candidate signals and risk rejections for review. It must not create order intents.
