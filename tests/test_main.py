from __future__ import annotations

import datetime as dt
import json
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


def write_session(sessions: Path, day: dt.date, keys: list[str], gap_ns: int = 200_000_000) -> None:
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


def test_until_moves_the_wpm_windows_off_the_current_date(sessions_dir: Path) -> None:
    anchor = dt.date.today() - dt.timedelta(days=90)
    write_session(sessions_dir, anchor - dt.timedelta(days=1), list('abcdefghij'))

    output = run('report', '--since', (anchor - dt.timedelta(days=30)).isoformat(), '--until', anchor.isoformat())

    assert '  WPM (7d):     0.0' not in output
    assert '  WPM (30d):    0.0' not in output


def test_wpm_windows_stay_anchored_to_today_without_until(sessions_dir: Path) -> None:
    write_session(sessions_dir, dt.date.today() - dt.timedelta(days=91), list('abcdefghij'))

    output = run('report', '--since', '2000-01-01')

    assert '  WPM (7d):     0.0' in output
    assert '  WPM (30d):    0.0' in output


def test_problems_reads_only_the_days_the_window_covers(sessions_dir: Path) -> None:
    write_session(sessions_dir, dt.date(2026, 6, 22), WORD_KEYS['quirk'])
    write_session(sessions_dir, dt.date(2026, 6, 23), WORD_KEYS['zap'])

    output = run('problems', '--since', '2026-06-01', '--until', '2026-06-22')

    assert 'quirk' in output
    assert 'zap' not in output
