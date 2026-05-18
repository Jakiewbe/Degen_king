"""Config validation helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from degenking.config.loader import load_config


def validate_config_file(path: str | Path) -> tuple[bool, str]:
    """Validate a config file and return a CLI-friendly result."""

    try:
        config = load_config(path)
    except (OSError, ValueError, ValidationError) as exc:
        return False, str(exc)
    return True, config.config_hash or ""
