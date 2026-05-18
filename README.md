# DegenKing

Safe, auditable MVP for crypto spot-perpetual funding arbitrage.

Status: Phase 0 scaffolding and specifications.

## MVP Scope

Included:

- One exchange target: Bybit demo/testnet, read-only first.
- One strategy: spot-perpetual funding arbitrage.
- Symbols: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`.
- Modes: `monitor` and `paper`.
- Deterministic strategy, risk, order-intent, paper-fill, reconciliation, and audit design.

Excluded:

- Live trading.
- Real order placement.
- Cross-exchange arbitrage.
- Dashboard or UI.
- Autonomous agent execution.
- Any LLM access to exchange, execution, broker, order-client, or config mutation modules.

This repository is for engineering architecture and risk-controlled automation. It is not financial advice.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

The package currently contains skeleton modules only. Exchange API integration and paper-trading behavior are future phases.

## Package Layout

```text
src/degenking/
  app.py              CLI placeholder
  config/             Immutable config loading and validation
  common/             IDs, time, money helpers, shared enums
  audit/              Audit event contracts and sinks
  persistence/        Database models and repositories
  market_data/        Read-only market data contracts
  strategy/           Funding arbitrage signal contracts
  risk/               Layered risk policy contracts
  orders/             OrderIntent and idempotency contracts
  paper/              Paper broker contracts
  reconciliation/     Startup and runtime reconciliation contracts
  positions/          Position and PnL contracts
  reporting/          Read-only reporting views
  agent/              Import-isolated read-only analysis consumers
```

## Documentation

- [Architecture](docs/architecture.md)
- [Strategy: Funding Arbitrage](docs/strategy_funding_arbitrage.md)
- [Risk Policy](docs/risk_policy.md)
- [Order State Machine](docs/order_state_machine.md)
- [Data Model](docs/data_model.md)
- [Operations Runbook](docs/operations_runbook.md)
- [Live Readiness Checklist](docs/live_readiness_checklist.md)
