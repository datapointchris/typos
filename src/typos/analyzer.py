from __future__ import annotations

import datetime as dt
import statistics
from array import array
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from itertools import chain
from itertools import pairwise


def window_end(today: dt.date | None = None) -> dt.date:
    """The exclusive edge of a window that runs through today, which is tomorrow."""
    return (today or dt.date.today()) + dt.timedelta(days=1)


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
    """One bigram's count and every interval it was typed in, ascending."""

    bigram: str
    count: int = 0
    ikis_ns: array[int] = field(default_factory=lambda: array('q'))

    @property
    def median_iki_ns(self) -> int:
        return int(median_of_sorted([self.ikis_ns])) if self.ikis_ns else 0


@dataclass
class Reconstruction:
    """One session's final text, when each character of it was typed, and its corrections.

    `typed_at_ns[i]` is the `ts_ns` of `text[i]`. A report holds every session of its
    window at once, so the timings are one machine integer each rather than a tuple per character.
    """

    text: str
    typed_at_ns: array[int]
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


def trailing_word(chars: Sequence[str]) -> str:
    """Return the contiguous run of non-whitespace chars at the end of `chars`."""
    word: list[str] = []
    for c in reversed(chars):
        if c in ' \n\t':
            break
        word.append(c)
    return ''.join(reversed(word))


def reconstruct(events: Iterable[dict]) -> Reconstruction:
    chars: list[str] = []
    typed_at_ns = array('q')
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
                    word_context=trailing_word(chars),
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
            if not chars:
                continue
            if pending_insertions:
                # Already retyping after a delete; finalize that correction first
                # before treating this BS as the start of a new burst.
                flush()
            if pending_start_ts is None:
                pending_start_ts = ts
            typed_at_ns.pop()
            pending_deletions.append(chars.pop())
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
        chars.append(char)
        typed_at_ns.append(ts)
        if pending_deletions:
            pending_insertions.append(char)

    flush()

    return Reconstruction(text=''.join(chars), typed_at_ns=typed_at_ns, corrections=corrections)


def bigram_stats(*sessions: Reconstruction) -> dict[str, BigramStats]:
    """Count and time each adjacent pair of characters within a session, never across two."""
    stats: dict[str, BigramStats] = {}
    for session in sessions:
        for (c1, t1), (c2, t2) in pairwise(zip(session.text, session.typed_at_ns, strict=True)):
            bg = c1 + c2
            entry = stats.get(bg)
            if entry is None:
                entry = stats[bg] = BigramStats(bigram=bg)
            entry.count += 1
            entry.ikis_ns.append(t2 - t1)
    for entry in stats.values():
        entry.ikis_ns = array('q', sorted(entry.ikis_ns))
    return stats


def kth_smallest(sorted_runs: Sequence[array[int]], k: int) -> int:
    """The k-th smallest value, counting from 0, across runs that are each ascending.

    It bisects the range of values, counting how many in each run fall at or below the
    midpoint, so it holds nothing beyond the runs. Sorting them together, as
    `statistics.median` would, copies every interval of the window into a Python int.
    """
    lo = min(run[0] for run in sorted_runs if run)
    hi = max(run[-1] for run in sorted_runs if run)
    while lo < hi:
        mid = (lo + hi) // 2
        if sum(bisect_right(run, mid) for run in sorted_runs) > k:
            hi = mid
        else:
            lo = mid + 1
    return lo


def median_of_sorted(sorted_runs: Sequence[array[int]]) -> float:
    """`statistics.median` of every value across runs that are each ascending."""
    n = sum(map(len, sorted_runs))
    middle = n // 2
    if n % 2:
        return kth_smallest(sorted_runs, middle)
    return (kth_smallest(sorted_runs, middle - 1) + kth_smallest(sorted_runs, middle)) / 2


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

    @property
    def active_ns(self) -> int:
        """Time spent inside typing bursts, with every pause over `BURST_THRESHOLD_NS` left out."""
        return sum(sum(burst_ikis(s.typed_at_ns)) for s in self.sessions)

    def wpm(self) -> float | None:
        """Active-time WPM: chars/5 over burst minutes.

        None when the sessions hold no active typing time, so an empty window reads apart from a
        measured zero.
        """
        active_ns = self.active_ns
        if active_ns == 0:
            return None
        minutes = active_ns / 1_000_000_000 / 60
        return (self.chars / 5) / minutes

    def iki_variance(self) -> float | None:
        """Population variance of typing-burst IKIs (ns²), pooled across sessions.

        None with fewer than two intervals, where no variance was measured.
        """
        ikis = array('q', chain.from_iterable(burst_ikis(s.typed_at_ns) for s in self.sessions))
        if len(ikis) < 2:
            return None
        return statistics.pvariance(ikis)

    def bigram_stats(self) -> dict[str, BigramStats]:
        return bigram_stats(*self.sessions)

    def mistyped_words(self) -> list[WordMisstats]:
        return mistyped_words('\n'.join(s.text for s in self.sessions), self.corrections)


def reconstruct_sessions(sessions: Iterable[Iterable[dict]]) -> WindowReconstruction:
    return WindowReconstruction(sessions=[reconstruct(events) for events in sessions])


def damage_scores(stats: dict[str, BigramStats]) -> list[DamageScore]:
    runs = [bg.ikis_ns for bg in stats.values()]
    if not any(runs):
        return []
    baseline = median_of_sorted(runs)

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


def burst_ikis(typed_at_ns: Iterable[int]) -> Iterator[int]:
    """The typing-burst IKIs (in ns) between consecutive typed characters.

    ts_ns from vim.uv.hrtime() is monotonic-since-boot, so IKIs are only
    meaningful within one session — callers pass one session's timings at a time.
    """
    for t1, t2 in pairwise(typed_at_ns):
        gap = t2 - t1
        if 0 < gap < BURST_THRESHOLD_NS:
            yield gap


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
