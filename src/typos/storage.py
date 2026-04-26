from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from typos.config import sessions_dir

DATE_FROM_FILENAME = re.compile(r'(\d{4}-\d{2}-\d{2})\.jsonl$')


def parse_session_date(path: Path) -> date | None:
    m = DATE_FROM_FILENAME.search(path.name)
    if m is None:
        return None
    return date.fromisoformat(m.group(1))


def list_session_files(since: date | None = None, until: date | None = None) -> list[Path]:
    sd = sessions_dir()
    if not sd.exists():
        return []
    files = sorted(sd.glob('*.jsonl'))
    if since is None and until is None:
        return files
    out: list[Path] = []
    for f in files:
        d = parse_session_date(f)
        if d is None:
            continue
        if since is not None and d < since:
            continue
        if until is not None and d >= until:
            continue
        out.append(f)
    return out


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    # errors='replace' guards against rare non-UTF-8 keys (vim's K_SPECIAL
    # internal codes occasionally slip past keytrans on terminal-only keys).
    # Malformed JSON lines are skipped silently — the capture layer should
    # be the source of truth for log integrity.
    with path.open(encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_all_events(since: date | None = None, until: date | None = None) -> Iterator[dict[str, Any]]:
    for path in list_session_files(since=since, until=until):
        yield from iter_events(path)


def days_active(since: date | None = None, until: date | None = None) -> int:
    return len({d for f in list_session_files(since=since, until=until) if (d := parse_session_date(f)) is not None})


def append_event(event: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(event))
        f.write('\n')
