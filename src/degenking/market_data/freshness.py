"""Freshness checks for read-only market data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from degenking.common.enums import FreshnessStatus
from degenking.common.time import age_ms, utc_now


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    status: FreshnessStatus
    age_ms: int
    max_age_ms: int
    reason: str | None = None

    @property
    def is_fresh(self) -> bool:
        return self.status == FreshnessStatus.FRESH


def check_freshness(
    observed_at: datetime,
    *,
    max_age_ms: int,
    now: datetime | None = None,
) -> FreshnessResult:
    """Check whether an observed timestamp is within the configured max age."""

    reference = now or utc_now()
    current_age_ms = age_ms(observed_at, now=reference)
    if current_age_ms <= max_age_ms:
        return FreshnessResult(
            status=FreshnessStatus.FRESH,
            age_ms=current_age_ms,
            max_age_ms=max_age_ms,
        )
    return FreshnessResult(
        status=FreshnessStatus.STALE,
        age_ms=current_age_ms,
        max_age_ms=max_age_ms,
        reason=f"data age {current_age_ms}ms exceeds max {max_age_ms}ms",
    )
