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
    with path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            yield json.loads(line)


def iter_all_events() -> Iterator[dict[str, Any]]:
    for path in list_session_files():
        yield from iter_events(path)


def append_event(event: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(event))
        f.write('\n')
