from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from itertools import pairwise

SINCE_RELATIVE = re.compile(r'^(\d+)d$')


def window_end(today: dt.date | None = None) -> dt.date:
    """The exclusive edge of a window that runs through today, which is tomorrow."""
    return (today or dt.date.today()) + dt.timedelta(days=1)


def parse_since(value: str | None, anchor: dt.date) -> dt.date | None:
    """Read `<N>d` as N days before `anchor`, and YYYY-MM-DD as the date it names."""
    if value is None:
        return None
    m = SINCE_RELATIVE.match(value)
    if m:
        return anchor - dt.timedelta(days=int(m.group(1)))
    return dt.date.fromisoformat(value)


def resolve_window(
    since: str | None,
    until: str | None,
    today: dt.date | None = None,
) -> tuple[dt.date | None, dt.date | None]:
    """Resolve a --since/--until pair into the half-open date window [since, until).

    A window holds exactly as many days as it names. With no `until` it runs
    through today, so its exclusive edge is tomorrow and a relative date counts
    back from there: `--since 7d` is the last seven days, today included, and
    `--until 7d` leaves out exactly those seven. A given `until` is the report's
    frame of reference instead: `--since 7d --until 2026-07-01` asks about
    2026-06-24 through 2026-06-30. An absolute `since` is unaffected, and with no
    `until` the window has no upper bound.
    """
    end = window_end(today)
    until_date = parse_since(until, anchor=end)
    return parse_since(since, anchor=until_date or end), until_date


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
    word_context: str = ''


@dataclass
class WordMisstats:
    word: str
    typed: int
    corrections: int

    @property
    def rate(self) -> float:
        return self.corrections / self.typed if self.typed else 0.0


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


@dataclass
class DamageDelta:
    bigram: str
    prior_score: float
    current_score: float
    delta_pct: float


def normalize_key(key: str) -> str | None:
    if key in SPECIAL_TO_CHAR:
        return SPECIAL_TO_CHAR[key]
    if len(key) == 1:
        return key
    return None


def trailing_word(buffer: list[tuple[str, int]]) -> str:
    """Return the contiguous run of non-whitespace chars at the end of the buffer."""
    chars: list[str] = []
    for c, _ in reversed(buffer):
        if c in ' \n\t':
            break
        chars.append(c)
    return ''.join(reversed(chars))


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
                    word_context=trailing_word(buffer),
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
        if pending_deletions and char in ' \n\t':
            # Word boundary while a correction is in flight — finalize the
            # correction against the word being typed BEFORE the boundary
            # char joins the buffer. Otherwise trailing_word reads the empty
            # space and word_context comes back blank.
            flush()
        buffer.append((char, ts))
        if pending_deletions:
            pending_insertions.append(char)

    flush()

    text = ''.join(c for c, _ in buffer)
    return Reconstruction(text=text, char_timings=buffer, corrections=corrections)


def bigram_stats(*runs: list[tuple[str, int]]) -> dict[str, BigramStats]:
    """Count and time each adjacent pair of characters within a run, never across two."""
    stats: dict[str, BigramStats] = {}
    for char_timings in runs:
        for (c1, t1), (c2, t2) in pairwise(char_timings):
            bg = c1 + c2
            entry = stats.setdefault(bg, BigramStats(bigram=bg))
            entry.count += 1
            entry.ikis_ns.append(t2 - t1)
    return stats


@dataclass
class WindowReconstruction:
    """Every session file in a window, each reconstructed on its own.

    `ts_ns` restarts at boot, so two keys from different files have no interval
    between them, and a backspace that opens one file cannot delete what another
    file typed. Each statistic that pairs keys or edits text is computed within
    one session and pooled afterwards.
    """

    sessions: list[Reconstruction]

    @property
    def chars(self) -> int:
        return sum(len(s.text) for s in self.sessions)

    @property
    def corrections(self) -> list[Correction]:
        return [c for s in self.sessions for c in s.corrections]

    def bigram_stats(self) -> dict[str, BigramStats]:
        return bigram_stats(*(s.char_timings for s in self.sessions))

    def mistyped_words(self) -> list[WordMisstats]:
        return mistyped_words('\n'.join(s.text for s in self.sessions), self.corrections)


def reconstruct_sessions(sessions: Iterable[Iterable[dict]]) -> WindowReconstruction:
    return WindowReconstruction(sessions=[reconstruct(events) for events in sessions])


def damage_scores(stats: dict[str, BigramStats]) -> list[DamageScore]:
    all_ikis = []
    for bg in stats.values():
        all_ikis.extend(bg.ikis_ns)
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


def compute_iki_variance(sessions: Iterable[Iterable[dict]]) -> float:
    """Population variance of typing-burst IKIs (ns²) across sessions."""
    all_ikis: list[int] = []
    for events in sessions:
        rec = reconstruct(events)
        all_ikis.extend(char_timing_burst_ikis(rec.char_timings))
    if len(all_ikis) < 2:
        return 0.0
    return statistics.pvariance(all_ikis)


def variance_ns_to_ms(variance_ns2: float) -> float:
    """Convert ns² variance to ms² for display."""
    return variance_ns2 / 1_000_000_000_000


def damage_deltas(
    prior_scores: list[DamageScore],
    current_scores: list[DamageScore],
    threshold: float = 0.2,
) -> tuple[list[DamageDelta], list[DamageDelta]]:
    """Classify per-bigram damage deltas as improved or worsened.

    Returns (improved, worsened). Each is sorted by magnitude of change, then
    by bigram — a bigram that falls out of the current window scores exactly
    -100%, so ties are the common case rather than the rare one, and the
    bigram breaks them into an order that does not move between runs.
    A bigram is improved when its current damage dropped by more than
    `threshold` (default 20%) relative to its prior damage, and worsened
    when it rose by the same. Bigrams missing from one window are skipped.
    """
    prior_map = {s.bigram: s.score for s in prior_scores}
    current_map = {s.bigram: s.score for s in current_scores}

    improved: list[DamageDelta] = []
    worsened: list[DamageDelta] = []
    for bg in prior_map.keys() & current_map.keys():
        prior = prior_map[bg]
        current = current_map[bg]
        if prior <= 0:
            continue
        delta_pct = (current - prior) / prior
        if delta_pct < -threshold:
            improved.append(DamageDelta(bigram=bg, prior_score=prior, current_score=current, delta_pct=delta_pct))
        elif delta_pct > threshold:
            worsened.append(DamageDelta(bigram=bg, prior_score=prior, current_score=current, delta_pct=delta_pct))

    improved.sort(key=lambda d: (d.delta_pct, d.bigram))
    worsened.sort(key=lambda d: (-d.delta_pct, d.bigram))
    return improved, worsened


def mistyped_words(text: str, corrections: list[Correction]) -> list[WordMisstats]:
    """Aggregate corrections by the word being typed when they fired."""
    word_counts = Counter(text.split())
    correction_counts = Counter(c.word_context for c in corrections if c.word_context)

    out: list[WordMisstats] = []
    for word, ccount in correction_counts.items():
        typed = max(word_counts.get(word, 0), ccount)
        out.append(WordMisstats(word=word, typed=typed, corrections=ccount))
    out.sort(key=lambda w: w.corrections, reverse=True)
    return out
