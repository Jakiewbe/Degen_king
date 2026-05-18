"""Read-only agent consumer — IMPORT ISOLATION ENFORCED.

This package may ONLY import from:
  - degenking.reporting
  - degenking.audit

It MUST NOT import:
  - degenking.market_data   (exchange connectivity)
  - degenking.strategy      (signal execution logic)
  - degenking.risk          (config mutation)
  - degenking.orders        (order state machine)
  - degenking.paper         (broker/execution)
  - degenking.reconciliation (order client)
  - degenking.positions     (live position mutation)
  - degenking.config        (config mutation)
  - degenking.persistence   (direct DB write access)

This boundary is statically enforced by the import-boundary test.
"""
