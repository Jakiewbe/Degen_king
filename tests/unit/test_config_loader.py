from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from degenking.common.enums import RuntimeMode
from degenking.config.loader import load_config


def test_monitor_example_config_loads() -> None:
    config = load_config(Path("configs/example.monitor.yaml"))

    assert config.mode == RuntimeMode.MONITOR
    assert config.exchange.name == "binance"
    assert config.exchange.readonly is True
    assert config.paper is None
    assert config.config_hash


def test_paper_example_config_loads() -> None:
    config = load_config(Path("configs/example.paper.yaml"))

    assert config.mode == RuntimeMode.PAPER
    assert config.paper is not None
    assert config.risk is not None
    assert config.kill_switch.enabled is True
    assert config.kill_switch.require_manual_reset is True
    assert config.config_hash


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "live.yaml"
    path.write_text(
        """
mode: live
exchange:
  name: binance
  environment: testnet
  readonly: true
symbols: [BTCUSDT]
market_data:
  max_tick_age_ms: 1500
  max_orderbook_age_ms: 1500
  max_funding_age_ms: 60000
  max_latency_ms: 750
strategy:
  funding_arbitrage:
    enabled: true
    min_net_edge_bps: 8
    min_funding_rate_bps: 5
    min_seconds_to_funding: 900
    max_seconds_to_funding: 25200
kill_switch:
  enabled: true
  mode: simulated
  require_manual_reset: true
agent:
  enabled: true
  read_sources: [audit_events, reporting_views]
  can_modify_config: false
  can_access_execution: false
persistence:
  backend: postgresql
logging:
  level: INFO
  format: json
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(path)


def test_non_readonly_exchange_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.yaml"
    text = Path("configs/example.monitor.yaml").read_text(encoding="utf-8")
    path.write_text(text.replace("readonly: true", "readonly: false"), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)
