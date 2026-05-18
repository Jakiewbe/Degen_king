"""ID helpers for traceable events."""

from __future__ import annotations

from uuid import uuid4


def new_trace_id() -> str:
    """Create an opaque trace identifier for one decision path."""

    return f"trace_{uuid4().hex}"


def new_run_id() -> str:
    """Create an opaque run identifier for one process invocation."""

    return f"run_{uuid4().hex}"
