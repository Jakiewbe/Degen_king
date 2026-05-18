# Operations Runbook

## MVP Startup

1. Load config.
2. Validate mode is `monitor` or `paper`.
3. Persist `config_versions`.
4. Run startup recovery.
5. If unresolved incidents exist, enter manual recovery lock.
6. Start market data collection or paper loop.

## Monitor Mode

- Collect read-only market data.
- Mark stale data when freshness thresholds fail.
- Persist signals and risk rejections.
- Never create order intents.

## Paper Mode

- Create order intents only after risk approval.
- Simulate fills locally.
- Reconcile fills into position state.
- Simulate kill-switch close/cancel behavior when triggered.
- Never submit exchange orders.

## Manual Recovery

Manual recovery is required after:

- Kill-switch activation with manual reset.
- Illegal state transition.
- Startup state mismatch.
- Unresolved residual exposure.
- Repeated reconciliation failure.

Recovery steps:

1. Inspect `risk_incidents`.
2. Run reconciliation.
3. Confirm no unresolved residual exposure.
4. Record operator acknowledgement in `manual_actions`.
5. Reset recovery lock.

## Incident Outputs

Each incident must include:

- `trace_id`
- affected symbol
- trigger condition
- action taken
- whether entries are blocked
- whether manual reset is required
