"""Startup recovery gates for paper state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from degenking.orders.intents import OrderIntent
from degenking.positions.manager import HedgedPosition, PositionState
from degenking.reconciliation.service import (
    ReconciliationResult,
    ReconciliationStatus,
)


class StartupRecoveryAction(StrEnum):
    """Startup action after loading existing paper state."""

    ALLOW_NEW_ENTRIES = "allow_new_entries"
    BLOCK_NEW_ENTRIES = "block_new_entries"
    REQUIRE_MANUAL_RECOVERY = "require_manual_recovery"


class StartupRecoveryIssueType(StrEnum):
    """Issue types that can block startup."""

    OPEN_INTENT = "open_intent"
    OPEN_POSITION = "open_position"
    DIRTY_RECONCILIATION = "dirty_reconciliation"
    MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"


@dataclass(frozen=True, slots=True)
class StartupRecoveryIssue:
    """One startup state issue requiring attention."""

    type: StartupRecoveryIssueType
    entity_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class StartupRecoveryDecision:
    """Decision for whether a process may create new entries after startup."""

    action: StartupRecoveryAction
    issues: tuple[StartupRecoveryIssue, ...]
    evaluated_at: datetime

    @property
    def new_entries_allowed(self) -> bool:
        """Whether strategy may create new paper entries."""

        return self.action == StartupRecoveryAction.ALLOW_NEW_ENTRIES

    @property
    def manual_recovery_required(self) -> bool:
        """Whether operator acknowledgement/recovery is required."""

        return self.action == StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY


def evaluate_startup_recovery(
    *,
    open_intents: tuple[OrderIntent, ...],
    positions: tuple[HedgedPosition, ...],
    reconciliation_results: tuple[ReconciliationResult, ...],
    evaluated_at: datetime,
) -> StartupRecoveryDecision:
    """Evaluate startup state and decide whether new entries are allowed."""

    issues: list[StartupRecoveryIssue] = []
    for intent in open_intents:
        if not intent.is_terminal:
            issues.append(
                StartupRecoveryIssue(
                    type=StartupRecoveryIssueType.OPEN_INTENT,
                    entity_id=intent.intent_id,
                    reason="non_terminal_intent_loaded_at_startup",
                )
            )

    for position in positions:
        if position.state == PositionState.OPEN and not position.is_flat:
            issues.append(
                StartupRecoveryIssue(
                    type=StartupRecoveryIssueType.OPEN_POSITION,
                    entity_id=position.symbol,
                    reason="open_position_loaded_at_startup",
                )
            )

    for result in reconciliation_results:
        if result.status != ReconciliationStatus.CLEAN:
            issues.append(
                StartupRecoveryIssue(
                    type=StartupRecoveryIssueType.DIRTY_RECONCILIATION,
                    entity_id=result.symbol,
                    reason="dirty_reconciliation_result_loaded_at_startup",
                )
            )
        if result.manual_recovery_required:
            issues.append(
                StartupRecoveryIssue(
                    type=StartupRecoveryIssueType.MANUAL_RECOVERY_REQUIRED,
                    entity_id=result.symbol,
                    reason="reconciliation_requires_manual_recovery",
                )
            )

    action = _action_for_issues(tuple(issues))
    return StartupRecoveryDecision(
        action=action,
        issues=tuple(issues),
        evaluated_at=evaluated_at,
    )


def _action_for_issues(
    issues: tuple[StartupRecoveryIssue, ...],
) -> StartupRecoveryAction:
    if not issues:
        return StartupRecoveryAction.ALLOW_NEW_ENTRIES
    if any(
        issue.type
        in {
            StartupRecoveryIssueType.DIRTY_RECONCILIATION,
            StartupRecoveryIssueType.MANUAL_RECOVERY_REQUIRED,
        }
        for issue in issues
    ):
        return StartupRecoveryAction.REQUIRE_MANUAL_RECOVERY
    return StartupRecoveryAction.BLOCK_NEW_ENTRIES
