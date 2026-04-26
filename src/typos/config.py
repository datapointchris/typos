from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path('~/shart/typing').expanduser()
DEFAULT_NOTES_ROOT = Path('~/notes').expanduser()


def data_dir() -> Path:
    return Path(os.environ.get('TYPOS_DATA_DIR', str(DEFAULT_DATA_DIR))).expanduser()


def sessions_dir() -> Path:
    return data_dir() / 'sessions'


def notes_root() -> Path:
    return Path(os.environ.get('TYPOS_NOTES_ROOT', str(DEFAULT_NOTES_ROOT))).expanduser()
