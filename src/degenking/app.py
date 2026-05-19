"""CLI entry point for DegenKing.

Modes: monitor (read-only), paper (simulated fills).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import click

from degenking.config.loader import load_config
from degenking.paper.fixtures import build_synthetic_opportunity_inputs
from degenking.paper.orchestrator import PaperEntryRunInputs, execute_paper_entry_run


@click.group()
def main() -> None:
    """DegenKing spot-perpetual funding arbitrage MVP."""


@main.command()
@click.option("--config", "config_path", default="configs/monitor.yaml")
def monitor(config_path: str) -> None:
    """Read-only market data collection. No orders placed."""
    config = load_config(config_path)
    if config.mode != "monitor":
        raise click.ClickException(f"expected monitor config, got {config.mode}")
    click.echo(f"Monitor config loaded: {config.config_hash}")
    click.echo("No exchange connection is started yet.")


@main.command()
@click.option("--config", "config_path", default="configs/paper.yaml")
def paper(config_path: str) -> None:
    """Paper trading with simulated fills. No real orders."""
    config = load_config(config_path)
    if config.mode != "paper":
        raise click.ClickException(f"expected paper config, got {config.mode}")
    click.echo(f"Paper config loaded: {config.config_hash}")
    click.echo("No paper broker loop is started yet.")


@main.command(name="paper-dry-run")
@click.option("--config", "config_path", default="configs/example.paper.yaml")
@click.option("--symbol", default="BTCUSDT")
@click.option("--notional", default="1000")
def paper_dry_run(config_path: str, symbol: str, notional: str) -> None:
    """Run one deterministic local paper-entry attempt. No exchange access."""

    config = load_config(config_path)
    if config.mode != "paper":
        raise click.ClickException(f"expected paper config, got {config.mode}")
    if config.paper is None:
        raise click.ClickException("paper config block is required")

    submitted_at = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    proposed_notional = Decimal(notional)
    opportunity_inputs = build_synthetic_opportunity_inputs(
        config,
        symbol=symbol,
        proposed_notional_quote=proposed_notional,
        evaluated_at=submitted_at,
    )
    result = execute_paper_entry_run(
        PaperEntryRunInputs(
            opportunity_inputs=opportunity_inputs,
            trace_id="trace_cli_dry_run",
            run_id="run_cli_dry_run",
            strategy_id="funding_v1",
            config_hash=config.config_hash or "unknown_config",
            submitted_at=submitted_at,
            spot_taker_fee_bps=Decimal(str(config.paper.taker_fee_bps)),
            perp_taker_fee_bps=Decimal(str(config.paper.taker_fee_bps)),
        )
    )

    click.echo("Paper dry run: local synthetic fixture")
    click.echo(f"config_hash={config.config_hash}")
    click.echo(f"symbol={result.opportunity.symbol}")
    click.echo(f"signal_should_enter={result.opportunity.signal.should_enter}")
    click.echo(f"risk_approved={result.opportunity.risk_decision.approved}")
    click.echo(f"allow_new_entry={result.risk_decision.allow_new_entry}")
    click.echo(f"risk_reasons={','.join(result.risk_decision.source_reasons) or 'none'}")
    click.echo(f"intents={len(result.intents)}")
    click.echo(f"fills={len(result.fills)}")
    click.echo(f"audit_events={len(result.audit_events)}")
    if result.pnl is not None:
        click.echo(f"total_pnl_quote={result.pnl.total_pnl_quote}")
        click.echo(f"delta_notional_quote={result.pnl.delta_notional_quote}")
    if result.reconciliation is not None:
        click.echo(f"reconciliation_status={result.reconciliation.status.value}")


@main.command()
def health() -> None:
    """Print system health summary."""
    click.echo("Health check: OK (Phase 0 - no subsystems running)")


@main.group()
def kill_switch() -> None:
    """Kill switch commands."""


@kill_switch.command()
def status() -> None:
    """Show kill switch status."""
    click.echo("Kill switch: DISARMED (Phase 0 - simulated only)")


@kill_switch.command()
@click.option("--reason", required=True)
def trigger(reason: str) -> None:
    """Trigger the kill switch."""
    click.echo(f"Kill switch TRIGGERED. Reason: {reason}")
    # TODO: Phase 1 - persist risk_incident, halt all new OrderIntent creation.


@kill_switch.command()
@click.option("--incident-id", required=True)
def acknowledge(incident_id: str) -> None:
    """Acknowledge a kill switch incident."""
    click.echo(f"Incident {incident_id} acknowledged.")
    # TODO: Phase 1 - persist manual_actions record.


@kill_switch.command()
def reset() -> None:
    """Reset the kill switch after acknowledgement."""
    click.echo("Kill switch reset. New entries allowed.")
    # TODO: Phase 1 - verify acknowledgement exists, reset kill switch state.


@main.group()
def reconcile() -> None:
    """Reconciliation commands."""


@reconcile.command()
@click.option("--full", is_flag=True)
@click.option("--since", default=None)
def run(full: bool, since: str | None) -> None:
    """Run reconciliation."""
    click.echo("Reconciliation: OK (Phase 0 - no state to reconcile)")
    # TODO: Phase 1 - cross-check intents, fills, and position state.


@reconcile.command()
@click.option("--last", is_flag=True)
def report(last: bool) -> None:
    """View reconciliation report."""
    click.echo("No reconciliation runs yet (Phase 0 skeleton).")


if __name__ == "__main__":
    main()
