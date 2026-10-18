"""`--since` and `--until` resolve to the half-open days of session files a read takes."""

from __future__ import annotations

import datetime as dt
import time

import pytest
import typer

from typos.window import resolved

NOW = dt.datetime(2026, 10, 18, 14, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
TODAY = dt.date(2026, 10, 18)


@pytest.fixture(autouse=True)
def new_york(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('TZ', 'America/New_York')
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize(
    ('since', 'until', 'first', 'last'),
    [
        ('30s', None, TODAY, None),
        ('10m', None, TODAY, None),
        ('15h', None, dt.date(2026, 10, 17), None),
        ('7d', None, dt.date(2026, 10, 11), None),
        ('2w', None, dt.date(2026, 10, 4), None),
        ('2026-10-01', '2026-10-01', dt.date(2026, 10, 1), dt.date(2026, 10, 2)),
        ('2026-10-01T23:30:00-04:00', None, dt.date(2026, 10, 1), None),
        (None, '1d', None, TODAY),
        (None, None, dt.date(2026, 10, 11), None),
    ],
)
def test_each_form_resolves_to_the_days_it_touches(since, until, first, last) -> None:
    assert resolved(since, until, NOW) == (first, last)


@pytest.mark.parametrize(
    ('since', 'until'),
    [
        ('6mo', None),
        ('1y', None),
        ('2026-10-01T09:00', None),
        ('2026-02-30', None),
        ('last tuesday', None),
        ('2999-01-01', None),
        ('1d', '2d'),
    ],
)
def test_a_value_naming_no_range_is_a_usage_error(since, until) -> None:
    with pytest.raises(typer.BadParameter):
        resolved(since, until, NOW)
