# Order State Machine

## Primary Object: OrderIntent

`OrderIntent` is the internal desired action before broker or exchange submission. In MVP it is consumed only by the paper broker.

Required fields:

- `intent_id`
- `trace_id`
- `run_id`
- `strategy_id`
- `config_hash`
- `idempotency_key`
- `symbol`
- `leg`: `spot_open`, `perp_open`, `spot_close`, `perp_close`, `cleanup`
- `side`
- `qty`
- `notional_quote`
- `limit_price`
- `state`
- `client_order_id`
- `exchange_order_id`, nullable in paper mode
- `created_at`
- `updated_at`

## Idempotency

`idempotency_key` represents one logical action. It prevents duplicate paper intents when a strategy run, retry, or recovery path is replayed.

`client_order_id` is generated for every intent and must be stable enough for reconciliation. A future live implementation will map it to `exchange_order_id`.

## Normal States

- `INTENT_CREATED`
- `RISK_APPROVED`
- `SUBMITTED_TO_PAPER_BROKER`
- `ACKNOWLEDGED`
- `PARTIALLY_FILLED`
- `FILLED`
- `RECONCILED`
- `POSITION_UPDATED`
- `CLOSED`

## Abnormal States

- `RISK_REJECTED`
- `DUPLICATE_SUPPRESSED`
- `STALE_CANCEL_REQUESTED`
- `CANCELLED`
- `TIMEOUT`
- `LEG_1_FILLED_LEG_2_FAILED`
- `RESIDUAL_EXPOSURE`
- `CLEANUP_REQUIRED`
- `CLEANUP_SUBMITTED`
- `FAILED_MANUAL_RECOVERY_REQUIRED`

## Transition Rules

- `monitor` mode must not create `OrderIntent`.
- `paper` mode may create `OrderIntent` only after risk approval.
- `SUBMITTED_TO_PAPER_BROKER` requires a unique `idempotency_key`.
- Any partial fill must create fill records and update residual quantity.
- Any residual exposure starts the unhedged exposure timer.
- Illegal transitions are rejected, logged, and move the system into manual recovery lock.

## Reconciliation

The reconciliation loop compares:

- Active order intents.
- Simulated orders.
- Fills.
- Position state.
- Risk incidents.

It writes `reconciliation_runs` and either confirms clean state or opens a risk incident.

## Startup Recovery

Startup recovery must:

- Load open order intents.
- Load non-terminal simulated orders.
- Load open positions.
- Load unresolved risk incidents.
- Rebuild expected position state from fills.
- Block new entries if expected and observed state differ.

## Disconnect Handling

When WebSocket data disconnects:

- Mark affected market data stale.
- Block new entries using Layer A checks.
- Run REST fallback reconciliation where available.
- Persist latency and status events.

## Stale Order And Residual Cleanup

Stale intents are cancelled or moved to cleanup depending on fill state. Residual exposure must be cleaned by a dedicated cleanup intent in paper mode and must remain blocked until reconciled.
