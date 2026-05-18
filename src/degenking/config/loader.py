"""Config loading and hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from degenking.config.models import RuntimeConfig


def load_config(path: str | Path) -> RuntimeConfig:
    """Load, validate, and hash a YAML runtime config."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError("runtime config must be a YAML mapping")

    config_hash = hash_config(raw)
    config = RuntimeConfig.model_validate(raw)
    return config.model_copy(update={"config_hash": config_hash})


def hash_config(raw_config: dict[str, Any]) -> str:
    """Return a stable sha256 hash for a config mapping."""

    canonical = json.dumps(raw_config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
