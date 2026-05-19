from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from degenking.app import main


def test_health_command() -> None:
    result = CliRunner().invoke(main, ["health"])

    assert result.exit_code == 0
    assert "Health check: OK" in result.output


def test_paper_dry_run_uses_example_config_and_rejects_safely() -> None:
    result = CliRunner().invoke(
        main,
        ["paper-dry-run", "--config", "configs/example.paper.yaml"],
    )

    assert result.exit_code == 0
    assert "Paper dry run: local synthetic fixture" in result.output
    assert "risk_approved=False" in result.output
    assert "allow_new_entry=False" in result.output
    assert "intents=0" in result.output
    assert "fills=0" in result.output


def test_paper_dry_run_can_execute_with_coherent_synthetic_depth(tmp_path: Path) -> None:
    config_text = Path("configs/example.paper.yaml").read_text(encoding="utf-8")
    config_path = tmp_path / "paper.yaml"
    config_path.write_text(
        config_text.replace("min_orderbook_depth_usd: 50000", "min_orderbook_depth_usd: 1000"),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["paper-dry-run", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "risk_approved=True" in result.output
    assert "allow_new_entry=True" in result.output
    assert "intents=2" in result.output
    assert "fills=2" in result.output
    assert "audit_events=9" in result.output
    assert "reconciliation_status=clean" in result.output
