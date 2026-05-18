"""CLI entry point for DegenKing.

Modes: monitor (read-only), paper (simulated fills).
"""

from __future__ import annotations

import click

from degenking.config.loader import load_config


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
