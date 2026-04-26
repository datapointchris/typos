from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from typos.config import sessions_dir


def list_session_files() -> list[Path]:
    sd = sessions_dir()
    if not sd.exists():
        return []
    return sorted(sd.glob('*.jsonl'))


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


def iter_all_events() -> Iterator[dict[str, Any]]:
    for path in list_session_files():
        yield from iter_events(path)


def append_event(event: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(event))
        f.write('\n')
