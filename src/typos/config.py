from __future__ import annotations

import os
from pathlib import Path


def _state_home() -> Path:
    """XDG state home, resolved then fallen back — never hardcoded.

    Captured sessions are state rather than data: they survive across runs, no
    human authored them, and deleting one changes what the analyzer reports
    instead of costing a recompute.
    """
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')


def data_dir() -> Path:
    """Where sessions are written and read.

    TYPOS_DATA_DIR is how a caller points this somewhere else — a synced
    directory, a scratch path for a test. The Neovim plugin resolves the same
    variable and the same fallback, because the two halves must agree on the path
    without either one knowing anything about the other's machine.
    """
    override = os.environ.get('TYPOS_DATA_DIR')
    if override:
        return Path(override).expanduser()
    return _state_home() / 'typos'


def sessions_dir() -> Path:
    return data_dir() / 'sessions'
