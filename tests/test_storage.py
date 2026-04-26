from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from typos.storage import append_event
from typos.storage import iter_events
from typos.storage import parse_session_date


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
