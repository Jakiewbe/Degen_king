from __future__ import annotations

from decimal import Decimal

from degenking.audit.events import AuditEvent
from degenking.audit.logger import JsonlAuditLogger, MemoryAuditLogger, append_many
from degenking.common.enums import EventSeverity


def test_memory_audit_logger_serializes_events() -> None:
    logger = MemoryAuditLogger()

    logger.append(
        AuditEvent(
            event_type="config_loaded",
            component="config",
            payload={"net_edge": Decimal("1.23")},
            trace_id="trace_test",
            severity=EventSeverity.INFO,
        )
    )

    events = logger.read_all()
    assert events[0]["trace_id"] == "trace_test"
    assert events[0]["payload"]["net_edge"] == "1.23"
    assert events[0]["severity"] == "info"


def test_jsonl_audit_logger_appends_in_order(tmp_path) -> None:
    logger = JsonlAuditLogger(tmp_path / "audit.jsonl")

    append_many(
        logger,
        [
            AuditEvent(event_type="first", component="test", payload={}, trace_id="trace_1"),
            AuditEvent(event_type="second", component="test", payload={}, trace_id="trace_2"),
        ],
    )

    events = logger.read_all()
    assert [event["event_type"] for event in events] == ["first", "second"]
    assert [event["trace_id"] for event in events] == ["trace_1", "trace_2"]
