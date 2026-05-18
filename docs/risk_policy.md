# Risk Policy

The risk engine has absolute veto power. No order intent may be created unless risk approval passes. In MVP, approvals feed paper intents only.

## Layer A: Pre-Trade Veto Checks

Trigger: a strategy candidate signal is produced.

| Trigger condition | Action | Persistence event | Blocks new entries? | Manual reset? |
| --- | --- | --- | --- | --- |
| Stale ticker, order book, funding, or account data | Reject signal | `risk_checks` | Symbol-level until fresh | No |
| Funding time too close or too far | Reject signal | `risk_checks` | No | No |
| `net_edge_bps` below threshold | Reject signal | `risk_checks` | No | No |
| Insufficient order book depth | Reject signal | `risk_checks` | No | No |
| Estimated slippage exceeds cap | Reject signal | `risk_checks` | No | No |
| Minimum notional or precision rounding fails | Reject signal | `risk_checks` | No | No |
| Balance or margin insufficient | Reject signal | `risk_checks` | No | No |
| Symbol or total exposure cap exceeded | Reject signal | `risk_checks` | Symbol-level | No |
| API latency above threshold | Reject signal | `risk_checks` and `latency_samples` | Symbol or global by severity | No |
| Exchange degraded or maintenance status | Reject signal | `exchange_status`, `risk_incidents` | Global | Maybe |
| Kill switch or manual recovery lock active | Reject signal | `risk_incidents` | Global | Yes |

## Layer B: In-Flight Execution Guards

Trigger: a paper `OrderIntent` has been approved and is not terminal.

| Trigger condition | Action | Persistence event | Blocks new entries? | Manual reset? |
| --- | --- | --- | --- | --- |
| Duplicate idempotency key | Suppress duplicate | `order_intents` | No | No |
| Intent timeout | Cancel stale paper intent | `risk_incidents`, `orders` | Symbol-level until reconciled | No |
| Partial fill exceeds tolerance | Reconcile residual quantity and create cleanup intent | `fills`, `reconciliation_runs`, `risk_incidents` | Symbol-level | Maybe |
| Leg 1 filled and leg 2 failed | Create cleanup intent, enter residual exposure state | `risk_incidents` | Symbol-level | Yes if unreconciled |
| Simulated fill slippage exceeds cap | Reject or cleanup depending fill state | `risk_checks`, `risk_incidents` | Symbol-level | Maybe |
| Illegal state transition | Enter manual recovery lock | `system_events`, `risk_incidents` | Global | Yes |

## Layer C: Position Monitoring Guards

Trigger: a paper position is open.

| Trigger condition | Action | Persistence event | Blocks new entries? | Manual reset? |
| --- | --- | --- | --- | --- |
| Hedge delta exceeds tolerance | Create cleanup or close candidate | `positions`, `risk_incidents` | Symbol-level | Maybe |
| Funding turns unfavorable | Create close candidate | `risk_checks` | No | No |
| Basis deteriorates beyond limit | Create close candidate | `risk_checks` | Symbol-level | No |
| Max holding time reached | Create close candidate | `risk_checks` | No | No |
| Daily loss breach | Trigger kill switch | `pnl_records`, `risk_incidents` | Global | Yes |
| Liquidation buffer below threshold | Trigger close or kill-switch path | `positions`, `risk_incidents` | Global by severity | Yes |

## Layer D: Global Kill Switch

Config shape:

```yaml
kill_switch:
  enabled: true
  mode: simulated
  require_manual_reset: true
```

In monitor and paper modes, the kill switch is simulated but fully tested. In future testnet/live modes, it must be enforceable.

| Trigger condition | Action | Persistence event | Blocks new entries? | Manual reset? |
| --- | --- | --- | --- | --- |
| Operator activates kill switch | Simulate cancel/close workflow and block entries | `risk_incidents`, `system_events` | Global | Yes |
| Daily loss breach | Simulate close workflow and block entries | `risk_incidents`, `pnl_records` | Global | Yes |
| Repeated reconciliation failures | Freeze new entries | `risk_incidents`, `reconciliation_runs` | Global | Yes |
| Exchange status critical | Freeze new entries | `exchange_status`, `risk_incidents` | Global | Yes |

## Layer E: Manual Recovery Lock

Trigger: unknown state, startup mismatch, unresolved residual exposure, illegal state transition, or kill switch requiring reset.

Action:

- Block new entries globally.
- Require operator acknowledgement in `manual_actions`.
- Require reconciliation to produce a clean expected-vs-observed state.
- Require explicit reset before paper trading resumes.

Persistence:

- `risk_incidents`
- `manual_actions`
- `reconciliation_runs`
- `system_events`
