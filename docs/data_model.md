# Data Model

The data model is PostgreSQL-oriented. SQLite may be used only as a local development convenience if schemas remain portable.

## Common Fields

Primary event and decision tables include:

- `id`
- `trace_id`
- `run_id`
- `strategy_id`
- `config_hash`
- `created_at`
- `updated_at`

Use `trace_id` for a single decision path, `run_id` for a process/run instance, `strategy_id` for strategy identity, and `config_hash` for reproducibility.

## Tables

| Table | Purpose | Key fields |
| --- | --- | --- |
| `config_versions` | Immutable config snapshots | `config_hash`, `mode`, `exchange`, `symbols`, `raw_config`, `validation_status` |
| `exchange_status` | Exchange health and maintenance state | `exchange`, `environment`, `status`, `maintenance`, `last_heartbeat_at` |
| `latency_samples` | REST/WebSocket latency records | `exchange`, `channel`, `latency_ms`, `measured_at` |
| `raw_exchange_events` | Raw inbound payloads for replay/debug | `source`, `channel`, `payload`, `received_at` |
| `market_ticks` | Normalized spot/perp prices | `symbol`, `market_type`, `bid`, `ask`, `mid`, `mark`, `index` |
| `orderbook_snapshots` | Depth snapshots | `symbol`, `market_type`, `bids`, `asks`, `depth_usd`, `checksum` |
| `funding_rates` | Funding data | `symbol`, `funding_rate`, `next_funding_time`, `funding_interval_seconds` |
| `account_snapshots` | Account-level read-only state | `equity`, `available_margin`, `account_mode` |
| `balance_snapshots` | Asset balances | `asset`, `wallet_balance`, `available_balance`, `locked_balance` |
| `signals` | Strategy candidates | `symbol`, `net_edge_quote`, `net_edge_bps`, `suggested_notional`, `status` |
| `risk_checks` | One row per risk check | `decision_id`, `check_name`, `passed`, `observed_value`, `limit_value`, `reason` |
| `risk_incidents` | Risk events requiring action | `incident_type`, `severity`, `trigger`, `action_taken`, `manual_reset_required` |
| `order_intents` | Internal desired actions | `idempotency_key`, `client_order_id`, `leg`, `side`, `qty`, `state` |
| `orders` | Paper or future exchange orders | `client_order_id`, `exchange_order_id`, `intent_id`, `state` |
| `fills` | Fill records | `order_id`, `intent_id`, `price`, `qty`, `fee`, `liquidity` |
| `positions` | Position state | `symbol`, `spot_qty`, `perp_qty`, `delta_qty`, `entry_basis_bps`, `state` |
| `pnl_records` | PnL attribution | `funding_pnl`, `trading_fees`, `slippage_cost`, `realized_pnl`, `unrealized_pnl` |
| `reconciliation_runs` | Expected-vs-observed checks | `started_at`, `completed_at`, `expected_state`, `observed_state`, `discrepancies` |
| `manual_actions` | Operator interventions | `actor`, `action`, `reason`, `affected_trace_id`, `affected_position_id` |
| `agent_reports` | Read-only agent outputs | `report_type`, `source_views`, `content`, `generated_at` |
| `system_events` | General system events | `component`, `severity`, `event_type`, `message`, `payload` |

## Integrity Rules

- Every signal must have at least one risk decision.
- Every order intent must have one `idempotency_key`.
- Every order must reference an order intent.
- Every fill must reference an order and reconcile into position state.
- Manual recovery resets must create `manual_actions`.
- Agent reports must reference reporting or audit sources only.
