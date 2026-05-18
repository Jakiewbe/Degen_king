# Live Readiness Checklist

Live trading is out of scope for MVP. A future live phase cannot start until all gates below pass.

- 7 consecutive days of paper trading logs.
- Zero illegal state transitions.
- Every signal has a risk decision.
- Every order intent has an idempotency key.
- Every simulated fill reconciles into position state.
- All kill-switch tests pass.
- All partial-fill and single-leg-failure tests pass.
- Manual recovery procedure is documented and tested.
- Agent package has no dependency on execution, exchange, broker, order-client, or config mutation modules.
- Testnet design review is completed.
- Production credential handling design is reviewed.
- Live notional caps and manual reset procedure are approved.
