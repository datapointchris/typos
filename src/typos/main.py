from __future__ import annotations

import typer
from rich.console import Console

from typos.config import data_dir
from typos.storage import list_session_files

typos_app = typer.Typer(no_args_is_help=True, help='Passive typing analysis from your real prose.')
console = Console()


@typos_app.command('status')
def status_cmd() -> None:
    """Show data location, session count, and capture state."""
    sessions = list_session_files()
    console.print(f'data dir: {data_dir()}')
    console.print(f'sessions: {len(sessions)}')
    if sessions:
        console.print(f'latest:   {sessions[-1].name}')


@typos_app.command('report')
def report_cmd() -> None:
    """Show typing report — WPM, damaging patterns, longitudinal deltas."""
    console.print('[yellow]not yet implemented[/yellow]')


@typos_app.command('problems')
def problems_cmd() -> None:
    """Show top damaging bigrams and most-mistyped words."""
    console.print('[yellow]not yet implemented[/yellow]')


@typos_app.command('generate')
def generate_cmd() -> None:
    """Generate practice text from current weak patterns."""
    console.print('[yellow]not yet implemented[/yellow]')
