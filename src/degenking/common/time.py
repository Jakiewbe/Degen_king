"""Timezone-safe time utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def age_ms(observed_at: datetime, *, now: datetime | None = None) -> int:
    """Return non-negative age in milliseconds for a UTC timestamp."""

    reference = now or utc_now()
    return max(0, int((reference - observed_at).total_seconds() * 1000))
