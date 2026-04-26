from __future__ import annotations

from collections import Counter

import typer
from rich.console import Console
from rich.table import Table

from typos.analyzer import bigram_stats
from typos.analyzer import damage_scores
from typos.analyzer import display_bigram
from typos.analyzer import parse_since
from typos.analyzer import reconstruct
from typos.config import data_dir
from typos.storage import days_active
from typos.storage import iter_all_events
from typos.storage import list_session_files

typos_app = typer.Typer(no_args_is_help=True, help='Passive typing analysis from your real prose.')
console = Console()


@typos_app.command('status')
def status_cmd() -> None:
    """Show data location, session count, and latest session file."""
    sessions = list_session_files()
    console.print(f'data dir: {data_dir()}')
    console.print(f'sessions: {len(sessions)}')
    if sessions:
        console.print(f'latest:   {sessions[-1].name}')


@typos_app.command('report')
def report_cmd(
    top: int = typer.Option(10, '--top', help='Number of bigrams to show.'),
    since: str = typer.Option('7d', '--since', help='Window: 7d / 30d (relative) or YYYY-MM-DD.'),
) -> None:
    """Show typing report — totals and top damaging bigrams."""
    cutoff = parse_since(since)
    sessions = list_session_files(since=cutoff)
    if not sessions:
        console.print(f'[yellow]no sessions in window (--since {since})[/yellow]')
        return

    events = list(iter_all_events(since=cutoff))
    rec = reconstruct(events)
    stats = bigram_stats(rec.char_timings)
    scores = damage_scores(stats)

    console.print(f'[bold]typos report — last {since}[/bold]')
    console.print(f'  sessions:     {len(sessions)}')
    console.print(f'  days active:  {days_active(since=cutoff)}')
    console.print(f'  total chars:  {len(rec.text):,}')
    console.print(f'  bigrams:      {len(stats):,}')
    console.print(f'  corrections:  {len(rec.corrections)}')
    console.print()

    if not scores:
        console.print('[yellow]no bigrams yet — type more to populate[/yellow]')
        return

    console.print(f'[bold]top {top} damaging bigrams[/bold]')
    table = Table(show_header=True, header_style='bold')
    table.add_column('bigram')
    table.add_column('count', justify='right')
    table.add_column('median ms', justify='right')
    table.add_column('damage', justify='right')
    for s in scores[:top]:
        table.add_row(
            display_bigram(s.bigram),
            str(s.count),
            f'{s.median_iki_ns / 1_000_000:.0f}',
            f'{s.score:.1f}',
        )
    console.print(table)


@typos_app.command('problems')
def problems_cmd(
    top: int = typer.Option(10, '--top', help='Number of corrections to show.'),
    since: str = typer.Option('7d', '--since', help='Window: 7d / 30d (relative) or YYYY-MM-DD.'),
) -> None:
    """Show top corrections — what you typed wrong and how you fixed it."""
    cutoff = parse_since(since)
    events = list(iter_all_events(since=cutoff))
    rec = reconstruct(events)
    if not rec.corrections:
        console.print('[yellow]no corrections detected yet[/yellow]')
        return

    counts = Counter((c.wrong, c.right) for c in rec.corrections)

    console.print(f'[bold]top {top} corrections[/bold]')
    table = Table(show_header=True, header_style='bold')
    table.add_column('wrong')
    table.add_column('right')
    table.add_column('count', justify='right')
    for (wrong, right), count in counts.most_common(top):
        table.add_row(
            display_bigram(wrong) or '(empty)',
            display_bigram(right) or '(empty)',
            str(count),
        )
    console.print(table)


@typos_app.command('generate')
def generate_cmd() -> None:
    """Generate practice text from current weak patterns."""
    console.print('[yellow]not yet implemented[/yellow]')
