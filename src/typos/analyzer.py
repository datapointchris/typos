from __future__ import annotations

import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import timedelta

SINCE_RELATIVE = re.compile(r'^(\d+)d$')


def parse_since(value: str | None, today: date | None = None) -> date | None:
    if value is None:
        return None
    today = today or date.today()
    m = SINCE_RELATIVE.match(value)
    if m:
        return today - timedelta(days=int(m.group(1)))
    return date.fromisoformat(value)


SPECIAL_TO_CHAR = {
    '<Space>': ' ',
    '<CR>': '\n',
    '<Tab>': '\t',
}

BACKSPACE = '<BS>'

# Inter-keystroke intervals longer than this count as idle and are excluded
# from WPM and IKI-variance calculations. 5 seconds covers thinking pauses
# inside a typing burst without folding in coffee breaks.
BURST_THRESHOLD_NS = 5_000_000_000


@dataclass
class Correction:
    wrong: str
    right: str
    start_ts_ns: int


@dataclass
class BigramStats:
    bigram: str
    count: int = 0
    ikis_ns: list[int] = field(default_factory=list)

    @property
    def median_iki_ns(self) -> int:
        return int(statistics.median(self.ikis_ns)) if self.ikis_ns else 0


@dataclass
class Reconstruction:
    text: str
    char_timings: list[tuple[str, int]]
    corrections: list[Correction]


@dataclass
class DamageScore:
    bigram: str
    count: int
    median_iki_ns: int
    score: float


def normalize_key(key: str) -> str | None:
    if key in SPECIAL_TO_CHAR:
        return SPECIAL_TO_CHAR[key]
    if len(key) == 1:
        return key
    return None


def reconstruct(events: Iterable[dict]) -> Reconstruction:
    buffer: list[tuple[str, int]] = []
    corrections: list[Correction] = []
    pending_deletions: list[str] = []
    pending_insertions: list[str] = []
    pending_start_ts: int | None = None

    def flush() -> None:
        nonlocal pending_start_ts
        if pending_deletions:
            corrections.append(
                Correction(
                    wrong=''.join(reversed(pending_deletions)),
                    right=''.join(pending_insertions),
                    start_ts_ns=pending_start_ts or 0,
                )
            )
        pending_deletions.clear()
        pending_insertions.clear()
        pending_start_ts = None

    for event in events:
        if event.get('mode') != 'i':
            flush()
            continue
        key = event['key']
        ts = event['ts_ns']

        if key == BACKSPACE:
            if not buffer:
                continue
            if pending_insertions:
                # Already retyping after a delete; finalize that correction first
                # before treating this BS as the start of a new burst.
                flush()
            if pending_start_ts is None:
                pending_start_ts = ts
            deleted_char, _ = buffer.pop()
            pending_deletions.append(deleted_char)
            continue

        char = normalize_key(key)
        if char is None:
            flush()
            continue
        buffer.append((char, ts))
        if pending_deletions:
            pending_insertions.append(char)

    flush()

    text = ''.join(c for c, _ in buffer)
    return Reconstruction(text=text, char_timings=buffer, corrections=corrections)


def bigram_stats(char_timings: list[tuple[str, int]]) -> dict[str, BigramStats]:
    stats: dict[str, BigramStats] = {}
    for i in range(len(char_timings) - 1):
        c1, t1 = char_timings[i]
        c2, t2 = char_timings[i + 1]
        bg = c1 + c2
        entry = stats.setdefault(bg, BigramStats(bigram=bg))
        entry.count += 1
        entry.ikis_ns.append(t2 - t1)
    return stats


def damage_scores(stats: dict[str, BigramStats]) -> list[DamageScore]:
    all_ikis = [iki for bg in stats.values() for iki in bg.ikis_ns]
    if not all_ikis:
        return []
    baseline = statistics.median(all_ikis)

    scores: list[DamageScore] = []
    for bg in stats.values():
        median = bg.median_iki_ns
        if median <= 0:
            continue
        slowdown = max(0, median - baseline)
        score = bg.count * slowdown / median
        scores.append(DamageScore(bigram=bg.bigram, count=bg.count, median_iki_ns=median, score=score))
    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


def display_bigram(bg: str) -> str:
    return bg.replace(' ', '␣').replace('\n', '↵').replace('\t', '⇥')


def char_timing_burst_ikis(char_timings: list[tuple[str, int]]) -> list[int]:
    """Extract typing-burst IKIs (in ns) from a char_timings list.

    ts_ns from vim.uv.hrtime() is monotonic-since-boot, so IKIs are only
    meaningful within one session — callers must group char_timings per session.
    """
    ikis: list[int] = []
    for i in range(len(char_timings) - 1):
        _, t1 = char_timings[i]
        _, t2 = char_timings[i + 1]
        gap = t2 - t1
        if 0 < gap < BURST_THRESHOLD_NS:
            ikis.append(gap)
    return ikis


def session_wpm_components(events: Iterable[dict]) -> tuple[int, int]:
    """Return (chars, active_ns) for events from a single boot session."""
    rec = reconstruct(events)
    return (len(rec.text), sum(char_timing_burst_ikis(rec.char_timings)))


def compute_wpm(sessions: Iterable[Iterable[dict]]) -> float:
    """Aggregate active-time WPM across sessions: chars/5 over burst minutes."""
    total_chars = 0
    total_active_ns = 0
    for events in sessions:
        chars, active_ns = session_wpm_components(events)
        total_chars += chars
        total_active_ns += active_ns
    if total_active_ns == 0:
        return 0.0
    minutes = total_active_ns / 1_000_000_000 / 60
    return (total_chars / 5) / minutes
