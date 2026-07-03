"""Orma CLI — command-line interface for local file versioning."""

import click

from orma import __version__


@click.group()
@click.version_option(version=__version__, prog_name="orma")
def main() -> None:
    """Orma — remembers every save of every tracked file."""


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
def track(directory: str) -> None:
    """Start tracking a directory for automatic file versioning."""
    click.echo(f"[stub] tracking: {directory}")


@main.command()
@click.argument("filepath", type=click.Path())
def history(filepath: str) -> None:
    """Show the version history of a tracked file."""
    click.echo(f"[stub] history: {filepath}")


@main.command()
@click.argument("filepath", type=click.Path())
@click.argument("version", type=int)
def restore(filepath: str, version: int) -> None:
    """Restore a file to a previous version."""
    click.echo(f"[stub] restore: {filepath} -> v{version}")
