from __future__ import annotations

import json
from datetime import date
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from typos.main import typos_app

runner = CliRunner()

# Corrections the reconstructor recovers as one word each, so a session can be
# identified in the output by which word it contributed.
WORD_KEYS = {
    'quirk': ['q', 'u', 'i', 'r', 'x', '<BS>', 'k'],
    'zap': ['z', 'a', 'x', '<BS>', 'p'],
}


@pytest.fixture
def sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty session store the CLI reads, with a wide console so lines do not wrap."""
    monkeypatch.setenv('TYPOS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('COLUMNS', '200')
    out = tmp_path / 'sessions'
    out.mkdir(parents=True)
    return out


def write_session(sessions: Path, day: date, keys: list[str], gap_ns: int = 200_000_000) -> None:
    ts = 1_000_000_000
    lines = []
    for key in keys:
        ts += gap_ns
        lines.append(json.dumps({'ts_ns': ts, 'key': key, 'mode': 'i', 'bufpath': '/x'}))
    (sessions / f'{day.isoformat()}.jsonl').write_text('\n'.join(lines) + '\n')


def run(*args: str) -> str:
    result = runner.invoke(typos_app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_report_excludes_a_session_dated_exactly_on_until(sessions_dir: Path) -> None:
    write_session(sessions_dir, date(2026, 6, 22), list('abcde'))
    write_session(sessions_dir, date(2026, 6, 23), list('fghij'))

    output = run('report', '--since', '2026-06-01', '--until', '2026-06-23')

    assert 'sessions:     1' in output
    assert 'total chars:  5' in output


def test_report_includes_a_session_dated_exactly_on_since(sessions_dir: Path) -> None:
    write_session(sessions_dir, date(2026, 6, 22), list('abcde'))
    write_session(sessions_dir, date(2026, 6, 23), list('fghij'))

    output = run('report', '--since', '2026-06-23', '--until', '2026-06-24')

    assert 'sessions:     1' in output
    assert 'total chars:  5' in output


def test_report_names_both_edges_of_a_closed_window(sessions_dir: Path) -> None:
    write_session(sessions_dir, date(2026, 6, 22), list('abcde'))

    output = run('report', '--since', '2026-06-01', '--until', '2026-06-23')

    assert '2026-06-01 to 2026-06-23 (exclusive)' in output


def test_until_moves_the_wpm_windows_off_the_current_date(sessions_dir: Path) -> None:
    anchor = date.today() - timedelta(days=90)
    write_session(sessions_dir, anchor - timedelta(days=1), list('abcdefghij'))

    output = run('report', '--since', '30d', '--until', anchor.isoformat())

    assert '  WPM (7d):     0.0' not in output
    assert '  WPM (30d):    0.0' not in output


def test_wpm_windows_stay_anchored_to_today_without_until(sessions_dir: Path) -> None:
    write_session(sessions_dir, date.today() - timedelta(days=91), list('abcdefghij'))

    output = run('report', '--since', '2000-01-01')

    assert '  WPM (7d):     0.0' in output
    assert '  WPM (30d):    0.0' in output


def test_a_relative_since_counts_back_from_until(sessions_dir: Path) -> None:
    anchor = date.today() - timedelta(days=90)
    write_session(sessions_dir, anchor - timedelta(days=3), list('abcde'))

    output = run('report', '--since', '7d', '--until', anchor.isoformat())

    assert 'sessions:     1' in output


def test_problems_excludes_a_session_dated_exactly_on_until(sessions_dir: Path) -> None:
    write_session(sessions_dir, date(2026, 6, 22), WORD_KEYS['quirk'])
    write_session(sessions_dir, date(2026, 6, 23), WORD_KEYS['zap'])

    output = run('problems', '--since', '2026-06-01', '--until', '2026-06-23')

    assert 'quirk' in output
    assert 'zap' not in output


def test_problems_includes_a_session_dated_exactly_on_since(sessions_dir: Path) -> None:
    write_session(sessions_dir, date(2026, 6, 22), WORD_KEYS['quirk'])
    write_session(sessions_dir, date(2026, 6, 23), WORD_KEYS['zap'])

    output = run('problems', '--since', '2026-06-23', '--until', '2026-06-24')

    assert 'zap' in output
    assert 'quirk' not in output
