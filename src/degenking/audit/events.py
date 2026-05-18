"""Audit event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from degenking.common.enums import EventSeverity
from degenking.common.ids import new_trace_id
from degenking.common.time import utc_now


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Append-only event used for traceable system decisions."""

    event_type: str
    component: str
    payload: dict[str, Any]
    trace_id: str = field(default_factory=new_trace_id)
    run_id: str | None = None
    strategy_id: str | None = None
    config_hash: str | None = None
    severity: EventSeverity = EventSeverity.INFO
    created_at: datetime = field(default_factory=utc_now)
