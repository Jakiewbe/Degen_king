"""Deterministic idempotency helpers for order intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from degenking.common.enums import RuntimeMode
from degenking.orders.intents import OrderIntentLeg, OrderSide

CLIENT_ORDER_ID_MAX_LENGTH = 36


def build_idempotency_key(
    *,
    mode: RuntimeMode,
    strategy_id: str,
    symbol: str,
    leg: OrderIntentLeg,
    side: OrderSide,
    logical_action_id: str,
) -> str:
    """Build a stable key for one logical desired action."""

    raw = "|".join(
        (
            mode.value,
            strategy_id,
            symbol,
            leg.value,
            side.value,
            logical_action_id,
        )
    )
    return f"idem_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def build_client_order_id(
    *,
    mode: RuntimeMode,
    strategy_id: str,
    symbol: str,
    leg: OrderIntentLeg,
    idempotency_key: str,
) -> str:
    """Build a deterministic client order id under common exchange limits."""

    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()[:14]
    prefix = _token(f"dk_{mode.value}_{strategy_id}_{symbol}_{leg.value}")
    return f"{prefix}_{digest}"[:CLIENT_ORDER_ID_MAX_LENGTH]


@dataclass(slots=True)
class IdempotencyLedger:
    """In-memory duplicate detector used by deterministic tests and paper mode."""

    seen_keys: set[str] = field(default_factory=set)

    def register(self, idempotency_key: str) -> bool:
        """Return False when the key was already registered."""

        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        if idempotency_key in self.seen_keys:
            return False
        self.seen_keys.add(idempotency_key)
        return True


def _token(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value.lower())
