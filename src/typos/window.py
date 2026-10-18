"""`--since` and `--until`: the days of sessions a read covers.

Each flag takes a span back from now (`30m`, `12h`, `7d`, `2w`, with `m` as
minutes), a day (`2026-10-01`), or an RFC 3339 instant carrying its offset.
Months and years have no fixed length, so neither is a unit. A day is read on
this machine's clock. On `--since` it opens at the day's first instant, and on
`--until` it runs to the next day's, so the whole day is inside.

A session file holds one day, and its keystrokes carry no clock time. So a read
takes every day file its window touches: `--since 12h` at 09:00 reads
yesterday's file and today's.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated

import typer

DEFAULT_SINCE = '7d'

SPAN = re.compile(r'(\d+)([smhdw])')
SPAN_UNITS = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks'}
CALENDAR = re.compile(r'\d+(mo|months?|M|y|years?|Y)')
DAY = re.compile(r'\d{4}-\d{2}-\d{2}')

Since = Annotated[
    str | None,
    typer.Option(
        '--since',
        show_default=DEFAULT_SINCE,
        help='Read from then: a span like 12h or 2w, a day like 2026-10-01, or an RFC 3339 instant.',
    ),
]

Until = Annotated[
    str | None,
    typer.Option('--until', help='Read up to then, in the same forms; a day includes all of it. Through today when omitted.'),
]


def bound(text: str, flag: str, now: dt.datetime, *, until: bool) -> dt.datetime:
    """The instant a `--since` or `--until` value names, or a usage error naming `flag`."""
    if CALENDAR.fullmatch(text):
        raise typer.BadParameter(
            f'{text!r} counts months or years, which have no fixed length; write weeks like 26w, or a day', param_hint=flag
        )
    span = SPAN.fullmatch(text)
    if span:
        try:
            return now - dt.timedelta(**{SPAN_UNITS[span[2]]: int(span[1])})
        except OverflowError:
            raise typer.BadParameter(f'{text!r} reaches back past year 1', param_hint=flag) from None
    if DAY.fullmatch(text):
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            raise typer.BadParameter(f'{text!r} is not a day on the calendar', param_hint=flag) from None
        if until:
            day += dt.timedelta(days=1)
        return dt.datetime.combine(day, dt.time.min).astimezone()
    try:
        instant = dt.datetime.fromisoformat(text)
    except ValueError:
        raise typer.BadParameter(
            f'{text!r} is not a span like 12h, a day like 2026-10-01, or an RFC 3339 instant', param_hint=flag
        ) from None
    if instant.tzinfo is None:
        raise typer.BadParameter(f'{text!r} carries no offset; write one, like {text}-04:00, or give a day', param_hint=flag)
    return instant


def first_day_from(moment: dt.datetime) -> dt.date:
    """The first day that opens at or after `moment`, on this machine's clock."""
    local = moment.astimezone()
    return local.date() if local.time() == dt.time.min else local.date() + dt.timedelta(days=1)


def resolved(
    since: str | None, until: str | None, now: dt.datetime, *, default: str = DEFAULT_SINCE
) -> tuple[dt.date | None, dt.date | None]:
    """The half-open days `[first, last)` of the session files the flags reach.

    `first` is None from the earliest session, and `last` is None through today.
    """
    if since is None and until is None:
        since = default
    end = bound(until, '--until', now, until=True) if until is not None else None
    start = bound(since, '--since', now, until=False) if since is not None else None
    if start is not None and start > now:
        raise typer.BadParameter(f'{start.isoformat()} is after now, so no session is in it yet', param_hint='--since')
    if start is not None and end is not None and start >= end:
        raise typer.BadParameter(f'{start.isoformat()} is not before {end.isoformat()}', param_hint='--since')
    first = start.astimezone().date() if start is not None else None
    last = first_day_from(end) if end is not None and end < now else None
    return first, last


def described(first: dt.date | None, last: dt.date | None) -> str:
    """The days a read covered, both edges inclusive."""
    opening = first.isoformat() if first is not None else 'the first session'
    closing = (last - dt.timedelta(days=1)).isoformat() if last is not None else 'today'
    return f'{opening} through {closing}'
