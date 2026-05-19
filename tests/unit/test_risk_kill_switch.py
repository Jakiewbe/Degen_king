"""Tests for pure kill-switch evaluation."""

from __future__ import annotations

import pytest

from degenking.common.enums import KillSwitchMode
from degenking.risk.kill_switch import (
    KillSwitchDecision,
    KillSwitchInputs,
    KillSwitchTrigger,
    evaluate_kill_switch,
)


def _make_inputs(
    *,
    enabled: bool = False,
    mode: KillSwitchMode = KillSwitchMode.SIMULATED,
    require_manual_reset: bool = False,
    triggers: tuple[KillSwitchTrigger, ...] = (),
    already_active: bool = False,
) -> KillSwitchInputs:
    return KillSwitchInputs(
        enabled=enabled,
        mode=mode,
        require_manual_reset=require_manual_reset,
        triggers=triggers,
        already_active=already_active,
    )


# ---------------------------------------------------------------------------
# Inactive default
# ---------------------------------------------------------------------------


def test_inactive_when_disabled_and_no_triggers() -> None:
    result = evaluate_kill_switch(_make_inputs())

    assert isinstance(result, KillSwitchDecision)
    assert result.active is False
    assert result.triggers == ()
    assert result.block_new_entries is False
    assert result.simulate_cancel_close is False
    assert result.enforce_cancel_close is False
    assert result.manual_reset_required is False
    assert result.reason is None


# ---------------------------------------------------------------------------
# Config enabled trigger
# ---------------------------------------------------------------------------


def test_config_enabled_trigger_activates() -> None:
    result = evaluate_kill_switch(_make_inputs(enabled=True))

    assert result.active is True
    assert KillSwitchTrigger.CONFIG_ENABLED in result.triggers
    assert result.block_new_entries is True


# ---------------------------------------------------------------------------
# Daily loss trigger
# ---------------------------------------------------------------------------


def test_daily_loss_trigger_activates() -> None:
    result = evaluate_kill_switch(
        _make_inputs(triggers=(KillSwitchTrigger.DAILY_LOSS_LIMIT,))
    )

    assert result.active is True
    assert KillSwitchTrigger.DAILY_LOSS_LIMIT in result.triggers
    assert result.block_new_entries is True


# ---------------------------------------------------------------------------
# Already active
# ---------------------------------------------------------------------------


def test_already_active_stays_active() -> None:
    result = evaluate_kill_switch(_make_inputs(already_active=True, enabled=False))

    assert result.active is True
    assert result.block_new_entries is True


def test_already_active_uses_manual_operator_when_no_triggers() -> None:
    result = evaluate_kill_switch(_make_inputs(already_active=True, enabled=False))

    assert KillSwitchTrigger.MANUAL_OPERATOR_REQUEST in result.triggers


def test_already_active_preserves_existing_triggers() -> None:
    result = evaluate_kill_switch(
        _make_inputs(
            already_active=True,
            triggers=(KillSwitchTrigger.EXCHANGE_CRITICAL,),
        )
    )

    assert result.active is True
    assert KillSwitchTrigger.EXCHANGE_CRITICAL in result.triggers


def test_already_active_deduplicates_existing_triggers() -> None:
    result = evaluate_kill_switch(
        _make_inputs(
            already_active=True,
            triggers=(
                KillSwitchTrigger.EXCHANGE_CRITICAL,
                KillSwitchTrigger.EXCHANGE_CRITICAL,
            ),
        )
    )

    assert result.triggers == (KillSwitchTrigger.EXCHANGE_CRITICAL,)


# ---------------------------------------------------------------------------
# Simulated mode
# ---------------------------------------------------------------------------


def test_simulated_mode_simulates_only() -> None:
    result = evaluate_kill_switch(_make_inputs(enabled=True, mode=KillSwitchMode.SIMULATED))

    assert result.simulate_cancel_close is True
    assert result.enforce_cancel_close is False


# ---------------------------------------------------------------------------
# Enforce mode
# ---------------------------------------------------------------------------


def test_enforce_mode_enforces_only() -> None:
    result = evaluate_kill_switch(_make_inputs(enabled=True, mode=KillSwitchMode.ENFORCE))

    assert result.enforce_cancel_close is True
    assert result.simulate_cancel_close is False


# ---------------------------------------------------------------------------
# Manual reset
# ---------------------------------------------------------------------------


def test_manual_reset_required_when_configured_and_active() -> None:
    result = evaluate_kill_switch(
        _make_inputs(enabled=True, require_manual_reset=True)
    )

    assert result.manual_reset_required is True


def test_no_manual_reset_when_configured_false() -> None:
    result = evaluate_kill_switch(
        _make_inputs(enabled=True, require_manual_reset=False)
    )

    assert result.manual_reset_required is False


def test_no_manual_reset_when_inactive() -> None:
    result = evaluate_kill_switch(
        _make_inputs(require_manual_reset=True)
    )

    assert result.manual_reset_required is False


# ---------------------------------------------------------------------------
# Multiple triggers
# ---------------------------------------------------------------------------


def test_multiple_triggers_retained() -> None:
    result = evaluate_kill_switch(
        _make_inputs(
            enabled=True,
            triggers=(
                KillSwitchTrigger.DAILY_LOSS_LIMIT,
                KillSwitchTrigger.RECONCILIATION_FAILURE,
                KillSwitchTrigger.EXECUTION_GUARD_FAILURE,
            ),
        )
    )

    assert result.active is True
    assert KillSwitchTrigger.CONFIG_ENABLED in result.triggers
    assert KillSwitchTrigger.DAILY_LOSS_LIMIT in result.triggers
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in result.triggers
    assert KillSwitchTrigger.EXECUTION_GUARD_FAILURE in result.triggers
    assert len(result.triggers) == 4


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_duplicate_triggers_are_deduplicated() -> None:
    result = evaluate_kill_switch(
        _make_inputs(
            enabled=True,
            triggers=(KillSwitchTrigger.DAILY_LOSS_LIMIT, KillSwitchTrigger.DAILY_LOSS_LIMIT),
        )
    )

    assert list(result.triggers).count(KillSwitchTrigger.DAILY_LOSS_LIMIT) == 1


# ---------------------------------------------------------------------------
# Invalid mode
# ---------------------------------------------------------------------------


def test_invalid_mode_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid kill_switch mode"):
        evaluate_kill_switch(
            KillSwitchInputs(
                enabled=True,
                mode="bogus",  # type: ignore[arg-type]
                require_manual_reset=False,
            )
        )


# ---------------------------------------------------------------------------
# Reason string
# ---------------------------------------------------------------------------


def test_reason_contains_all_trigger_values() -> None:
    result = evaluate_kill_switch(
        _make_inputs(
            enabled=True,
            triggers=(KillSwitchTrigger.EXCHANGE_CRITICAL,),
        )
    )

    assert result.reason is not None
    assert "config_enabled" in result.reason
    assert "exchange_critical" in result.reason


def test_reason_is_none_when_inactive() -> None:
    result = evaluate_kill_switch(_make_inputs())

    assert result.reason is None


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_kill_switch_decision_is_frozen() -> None:
    decision = KillSwitchDecision(
        active=True,
        mode=KillSwitchMode.SIMULATED,
        triggers=(KillSwitchTrigger.CONFIG_ENABLED,),
        block_new_entries=True,
        simulate_cancel_close=True,
        enforce_cancel_close=False,
        manual_reset_required=False,
        reason="config_enabled",
    )
    raised = False
    try:
        decision.active = False  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised
