from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterator

import typer
from rich.console import Console
from rich.table import Table

from typos import installed_commit
from typos import tool_version
from typos.analyzer import compute_iki_variance
from typos.analyzer import compute_wpm
from typos.analyzer import damage_deltas
from typos.analyzer import damage_scores
from typos.analyzer import display_bigram
from typos.analyzer import reconstruct_sessions
from typos.analyzer import resolve_window
from typos.analyzer import variance_ns_to_ms
from typos.analyzer import window_end
from typos.config import data_dir
from typos.storage import days_active
from typos.storage import iter_events
from typos.storage import list_session_files


def per_session_events(since: dt.date | None = None, until: dt.date | None = None) -> Iterator[list[dict]]:
    """Yield event-lists, one per session file, within the given window."""
    for path in list_session_files(since=since, until=until):
        yield list(iter_events(path))


def describe_window(since: str, cutoff: dt.date | None, until_cutoff: dt.date | None) -> str:
    """Name the analysed window, spelling out both edges once one is closed."""
    if until_cutoff is None:
        return f'last {since}'
    return f'{cutoff} to {until_cutoff} (exclusive)'


def format_iki_variance(current_ns2: float, prior_ns2: float) -> str:
    current = variance_ns_to_ms(current_ns2)
    prior = variance_ns_to_ms(prior_ns2)
    if current == 0 and prior == 0:
        return '—'
    if prior == 0:
        return f'{current:.0f}ms²'
    direction = 'down' if current < prior else 'up'
    return f'{current:.0f}ms²  ({direction} from {prior:.0f}ms² last week)'


ROOT_HELP = """Passive typing analysis from your real prose.

Start with `typos status` to confirm capture is writing sessions, then read `typos report`.

`report` and `problems` both list mistyped words. `report` is the weekly read: totals,
the bigrams costing you the most time, and the top words beneath them. Reach for
`problems --raw` when a word there needs the exact wrong-for-right keys behind it.

Examples:

  typos report

  typos report --since 30d

  typos problems --raw
"""

typos_app = typer.Typer(no_args_is_help=True, help=ROOT_HELP)
console = Console()


def version_callback(asked: bool) -> None:
    """Print `typos <version>`, with the commit after it for a git install, and exit."""
    if not asked:
        return
    commit = installed_commit()
    typer.echo(f'typos {tool_version()}' + (f' @ {commit[:8]}' if commit else ''))
    raise typer.Exit()


@typos_app.callback()
def root(
    version: bool | None = typer.Option(
        None, '--version', callback=version_callback, is_eager=True, help='Show the installed version and exit.'
    ),
) -> None:
    """Host the options that come before any command."""


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
    since: str = typer.Option('7d', '--since', help='Start of the window, inclusive: <N>d (relative) or YYYY-MM-DD.'),
    until: str | None = typer.Option(
        None,
        '--until',
        help='End of the window, exclusive: <N>d (relative) or YYYY-MM-DD. Every window the report derives ends here.',
    ),
) -> None:
    """Show typing report — totals and top damaging bigrams."""
    cutoff, until_cutoff = resolve_window(since, until)
    sessions = list_session_files(since=cutoff, until=until_cutoff)
    if not sessions:
        console.print(f'[yellow]no sessions in window ({describe_window(since, cutoff, until_cutoff)})[/yellow]')
        return

    window = reconstruct_sessions(per_session_events(since=cutoff, until=until_cutoff))
    stats = window.bigram_stats()
    scores = damage_scores(stats)

    anchor = until_cutoff or window_end()
    cutoff_7d = anchor - dt.timedelta(days=7)
    cutoff_14d = anchor - dt.timedelta(days=14)
    cutoff_30d = anchor - dt.timedelta(days=30)
    wpm_7d = compute_wpm(per_session_events(since=cutoff_7d, until=until_cutoff))
    wpm_30d = compute_wpm(per_session_events(since=cutoff_30d, until=until_cutoff))
    var_current = compute_iki_variance(per_session_events(since=cutoff_7d, until=until_cutoff))
    var_prior = compute_iki_variance(per_session_events(since=cutoff_14d, until=cutoff_7d))

    console.print(f'[bold]typos report — {describe_window(since, cutoff, until_cutoff)}[/bold]')
    console.print(f'  sessions:     {len(sessions)}')
    console.print(f'  days active:  {days_active(since=cutoff, until=until_cutoff)}')
    console.print(f'  total chars:  {window.chars:,}')
    console.print(f'  bigrams:      {len(stats):,}')
    console.print(f'  corrections:  {len(window.corrections)}')
    console.print(f'  WPM (7d):     {wpm_7d:.1f}')
    console.print(f'  WPM (30d):    {wpm_30d:.1f}')
    console.print(f'  IKI variance: {format_iki_variance(var_current, var_prior)}')
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

    words = window.mistyped_words()
    if words:
        console.print()
        console.print(f'[bold]top {top} mistyped words[/bold]')
        wtable = Table(show_header=True, header_style='bold')
        wtable.add_column('word')
        wtable.add_column('typed', justify='right')
        wtable.add_column('corrections', justify='right')
        wtable.add_column('rate', justify='right')
        for w in words[:top]:
            wtable.add_row(w.word, str(w.typed), str(w.corrections), f'{w.rate * 100:.0f}%')
        console.print(wtable)

    # Damage grows with how often a bigram is typed, so the deltas compare two
    # weeks of equal length whatever --since says. Scoring the whole window
    # against one week would report every bigram as worse on a 30-day report.
    prior_week = reconstruct_sessions(per_session_events(since=cutoff_14d, until=cutoff_7d))
    if prior_week.sessions:
        current_week = reconstruct_sessions(per_session_events(since=cutoff_7d, until=until_cutoff))
        prior_scores = damage_scores(prior_week.bigram_stats())
        current_scores = damage_scores(current_week.bigram_stats())
        improved, worsened = damage_deltas(prior_scores, current_scores)
        if improved:
            console.print()
            console.print('[bold]recently improved (damage down >20% week-over-week)[/bold]')
            for d in improved[:top]:
                console.print(f'  {display_bigram(d.bigram):<6}  {d.prior_score:.1f} → {d.current_score:.1f}')
        if worsened:
            console.print()
            console.print('[bold]recently worsened (damage up >20% week-over-week)[/bold]')
            for d in worsened[:top]:
                console.print(f'  {display_bigram(d.bigram):<6}  {d.prior_score:.1f} → {d.current_score:.1f}')


@typos_app.command('problems')
def problems_cmd(
    top: int = typer.Option(10, '--top', help='Number of items to show.'),
    since: str = typer.Option('7d', '--since', help='Start of the window, inclusive: <N>d (relative) or YYYY-MM-DD.'),
    until: str | None = typer.Option(
        None,
        '--until',
        help='End of the window, exclusive: <N>d (relative) or YYYY-MM-DD. A relative --since counts back from here.',
    ),
    raw: bool = typer.Option(False, '--raw', help='Show raw (wrong, right) pairs instead of word view.'),
) -> None:
    """Show your most-mistyped words (or raw correction pairs with --raw)."""
    cutoff, until_cutoff = resolve_window(since, until)
    window = reconstruct_sessions(per_session_events(since=cutoff, until=until_cutoff))
    corrections = window.corrections
    if not corrections:
        console.print('[yellow]no corrections detected yet[/yellow]')
        return

    if raw:
        counts = Counter((c.wrong, c.right) for c in corrections)
        console.print(f'[bold]top {top} correction pairs[/bold]')
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
        return

    words = window.mistyped_words()
    console.print(f'[bold]top {top} mistyped words[/bold]')
    table = Table(show_header=True, header_style='bold')
    table.add_column('word')
    table.add_column('typed', justify='right')
    table.add_column('corrections', justify='right')
    table.add_column('rate', justify='right')
    for w in words[:top]:
        table.add_row(w.word, str(w.typed), str(w.corrections), f'{w.rate * 100:.0f}%')
    console.print(table)
