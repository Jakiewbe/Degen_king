"""Append-only JSONL audit logger."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from degenking.audit.events import AuditEvent


class JsonlAuditLogger:
    """Small append-only JSONL audit sink.

    This logger is local-file based for MVP development. Production persistence
    can later mirror the same event shape into database tables.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: AuditEvent) -> None:
        """Append one audit event as a JSON line."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_to_jsonable(event), sort_keys=True) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        """Read all audit events from disk."""

        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


class MemoryAuditLogger:
    """In-memory audit sink for unit tests and dry runs."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def read_all(self) -> list[dict[str, Any]]:
        return [_to_jsonable(event) for event in self.events]


def append_many(logger: JsonlAuditLogger | MemoryAuditLogger, events: Iterable[AuditEvent]) -> None:
    """Append a sequence of audit events in order."""

    for event in events:
        logger.append(event)


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value
