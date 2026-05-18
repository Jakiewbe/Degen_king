"""Latency threshold helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LatencyCheck:
    latency_ms: int
    max_latency_ms: int
    passed: bool


def check_latency(latency_ms: int, *, max_latency_ms: int) -> LatencyCheck:
    """Return whether an API/WebSocket latency sample is within limit."""

    return LatencyCheck(
        latency_ms=latency_ms,
        max_latency_ms=max_latency_ms,
        passed=latency_ms <= max_latency_ms,
    )
