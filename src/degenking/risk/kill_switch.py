"""Layer D global kill-switch evaluation.

Pure functions that decide whether system-level risk events require
blocking all new entries, simulating cancellations, or enforcing them.

No broker calls. No order creation. No exchange access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from degenking.common.enums import KillSwitchMode


class KillSwitchTrigger(StrEnum):
    """System-level risk events that can activate the kill switch."""

    CONFIG_ENABLED = "config_enabled"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    EXCHANGE_CRITICAL = "exchange_critical"
    RECONCILIATION_FAILURE = "reconciliation_failure"
    EXECUTION_GUARD_FAILURE = "execution_guard_failure"
    MANUAL_OPERATOR_REQUEST = "manual_operator_request"


_VALID_MODES = frozenset({KillSwitchMode.SIMULATED, KillSwitchMode.ENFORCE})


@dataclass(frozen=True, slots=True)
class KillSwitchInputs:
    """All inputs needed to evaluate the global kill switch."""

    enabled: bool
    mode: KillSwitchMode
    require_manual_reset: bool
    triggers: tuple[KillSwitchTrigger, ...] = ()
    already_active: bool = False


@dataclass(frozen=True, slots=True)
class KillSwitchDecision:
    """Result of kill-switch evaluation."""

    active: bool
    mode: KillSwitchMode
    triggers: tuple[KillSwitchTrigger, ...]
    block_new_entries: bool
    simulate_cancel_close: bool
    enforce_cancel_close: bool
    manual_reset_required: bool
    reason: str | None = field(default=None)


def evaluate_kill_switch(inputs: KillSwitchInputs) -> KillSwitchDecision:
    """Evaluate the global kill switch from system-level risk triggers.

    Returns a KillSwitchDecision describing what actions to take.
    """
    if inputs.mode not in _VALID_MODES:
        raise ValueError(
            f"invalid kill_switch mode: {inputs.mode}; must be simulated or enforce"
        )

    triggers = _resolve_triggers(inputs)

    if not triggers:
        return KillSwitchDecision(
            active=False,
            mode=inputs.mode,
            triggers=(),
            block_new_entries=False,
            simulate_cancel_close=False,
            enforce_cancel_close=False,
            manual_reset_required=False,
            reason=None,
        )

    active = True
    block_new_entries = True
    simulate_cancel_close = inputs.mode == KillSwitchMode.SIMULATED
    enforce_cancel_close = inputs.mode == KillSwitchMode.ENFORCE
    manual_reset_required = active and inputs.require_manual_reset
    reason = ";".join(sorted(t.value for t in triggers))

    return KillSwitchDecision(
        active=active,
        mode=inputs.mode,
        triggers=triggers,
        block_new_entries=block_new_entries,
        simulate_cancel_close=simulate_cancel_close,
        enforce_cancel_close=enforce_cancel_close,
        manual_reset_required=manual_reset_required,
        reason=reason,
    )


def _resolve_triggers(inputs: KillSwitchInputs) -> tuple[KillSwitchTrigger, ...]:
    """Determine the effective trigger set from inputs."""
    triggers: list[KillSwitchTrigger] = []

    if inputs.already_active:
        return _dedupe_triggers(
            tuple(inputs.triggers)
            if inputs.triggers
            else (KillSwitchTrigger.MANUAL_OPERATOR_REQUEST,)
        )

    if inputs.enabled:
        triggers.append(KillSwitchTrigger.CONFIG_ENABLED)

    triggers.extend(inputs.triggers)

    return _dedupe_triggers(tuple(triggers))


def _dedupe_triggers(
    triggers: tuple[KillSwitchTrigger, ...],
) -> tuple[KillSwitchTrigger, ...]:
    seen: set[KillSwitchTrigger] = set()
    deduped: list[KillSwitchTrigger] = []
    for t in triggers:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return tuple(deduped)
