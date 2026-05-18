# Architecture

## MVP Control Path

```text
MarketData -> Strategy -> Risk -> OrderIntent -> PaperBroker -> Reconciliation -> PositionManager -> Audit
```

The MVP is intentionally narrow: monitor and paper trading only. It has no live order placement path.

## Scope Boundaries

Included in MVP:

- Binance testnet/read-only as the only first data-source target.
- Read-only market data and optional read-only account snapshots.
- Spot-perpetual funding arbitrage for `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`.
- Deterministic signal calculation, risk decisions, order intents, simulated fills, reconciliation, position state, and audit logs.

Excluded from MVP:

- Real exchange order placement.
- Live trading.
- Multi-exchange adapters as first-class implementation targets.
- Dashboard or UI.
- Cross-exchange perpetual arbitrage.
- LLM or agent access to exchange, execution, broker, order-client, or config mutation modules.

Bybit and OKX are future adapter targets only. The chosen first data source does
not determine the future execution venue.

## Components

| Component | Responsibility |
| --- | --- |
| `config` | Load immutable runtime config, validate mode boundaries, compute `config_hash`. |
| `market_data` | Define read-only Binance market/account snapshot contracts, freshness checks, and latency samples. |
| `strategy` | Generate funding-arbitrage candidate signals. No order creation. |
| `risk` | Apply layered vetoes and guards. Risk approval is required before any paper order intent. |
| `orders` | Define `OrderIntent`, idempotency keys, client order IDs, state transitions, and duplicate prevention. |
| `paper` | Simulate broker acknowledgements, fills, partial fills, fees, slippage, latency, and funding settlement. |
| `reconciliation` | Rebuild expected state from events, detect discrepancies, and trigger recovery locks. |
| `positions` | Track hedge delta, funding PnL, fees, slippage, basis, and exit conditions. |
| `persistence` | Store normalized data, decisions, orders, fills, incidents, and manual actions. |
| `audit` | Append-only event stream for traceability. |
| `reporting` | Read-only views consumed by operators and the agent package. |
| `agent` | Physically isolated reporting and diagnostics only. |

## Safety Invariants

- `monitor` mode cannot create `OrderIntent` records.
- `paper` mode can create `OrderIntent` records but cannot submit exchange orders.
- Every signal must have a persisted risk decision.
- Every order intent must have an `idempotency_key`.
- Every fill must reconcile into position state.
- Agent code must not import exchange, execution, paper broker, order state machine, order client, or config mutation modules.
- Kill switch is configured in all modes and is simulated in MVP.

## Future Progression

Future testnet and live execution require a separate design review and passing the live readiness checklist. No future phase may grant the agent direct execution authority.
