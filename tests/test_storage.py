from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from typos.storage import append_event
from typos.storage import days_active
from typos.storage import iter_all_events
from typos.storage import iter_events
from typos.storage import list_session_files
from typos.storage import parse_session_date


@pytest.fixture
def dated_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Point TYPOS_DATA_DIR at one session file per day across a five-day span."""
    days = ['2026-06-20', '2026-06-21', '2026-06-22', '2026-06-23', '2026-06-24']
    sessions = tmp_path / 'sessions'
    sessions.mkdir(parents=True)
    for day in days:
        (sessions / f'{day}.jsonl').write_text(json.dumps({'ts_ns': 1, 'key': 'a', 'mode': 'i', 'bufpath': '/x'}) + '\n')
    monkeypatch.setenv('TYPOS_DATA_DIR', str(tmp_path))
    return days


def test_append_and_iter_events(tmp_path: Path) -> None:
    log = tmp_path / 'sessions' / '2026-04-26.jsonl'
    append_event({'ts_ns': 1, 'key': 'a', 'bufpath': '/x', 'mode': 'i'}, log)
    append_event({'ts_ns': 2, 'key': 'b', 'bufpath': '/x', 'mode': 'i'}, log)

    events = list(iter_events(log))
    assert len(events) == 2
    assert events[0]['key'] == 'a'
    assert events[1]['key'] == 'b'


def test_iter_events_skips_blank_lines(tmp_path: Path) -> None:
    log = tmp_path / '2026-04-26.jsonl'
    log.write_text(json.dumps({'ts_ns': 1, 'key': 'a'}) + '\n\n' + json.dumps({'ts_ns': 2, 'key': 'b'}) + '\n')
    events = list(iter_events(log))
    assert len(events) == 2


def test_parse_session_date_extracts_iso_date() -> None:
    assert parse_session_date(Path('/x/sessions/2026-04-26.jsonl')) == date(2026, 4, 26)
    assert parse_session_date(Path('/x/sessions/not-dated.jsonl')) is None
    assert parse_session_date(Path('/x/sessions/2026-04-26-extra.jsonl')) is None


def test_the_window_includes_the_since_date_and_excludes_the_until_date(dated_sessions: list[str]) -> None:
    found = list_session_files(since=date(2026, 6, 21), until=date(2026, 6, 23))
    assert [p.stem for p in found] == ['2026-06-21', '2026-06-22']


def test_until_alone_excludes_its_own_date(dated_sessions: list[str]) -> None:
    found = list_session_files(until=date(2026, 6, 22))
    assert [p.stem for p in found] == ['2026-06-20', '2026-06-21']


def test_iter_all_events_and_days_active_honour_the_same_window(dated_sessions: list[str]) -> None:
    window = {'since': date(2026, 6, 21), 'until': date(2026, 6, 23)}
    assert len(list(iter_all_events(**window))) == 2
    assert days_active(**window) == 2
