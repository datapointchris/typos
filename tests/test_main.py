from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from typos.main import wpm_windows


@pytest.fixture
def sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty session store the CLI reads."""
    monkeypatch.setenv('TYPOS_DATA_DIR', str(tmp_path))
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


def test_wpm_windows_end_at_until_and_otherwise_at_today(sessions_dir: Path) -> None:
    typed_on = dt.date.today() - dt.timedelta(days=91)
    write_session(sessions_dir, typed_on, list('abcdefghij'))

    wpm_7d, wpm_30d = wpm_windows(until=typed_on + dt.timedelta(days=1))
    assert wpm_7d > 0
    assert wpm_30d > 0

    assert wpm_windows(until=None) == (0.0, 0.0)
