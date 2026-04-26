from __future__ import annotations

from datetime import date
from pathlib import Path

from typos.analyzer import bigram_stats
from typos.analyzer import damage_scores
from typos.analyzer import parse_since
from typos.analyzer import reconstruct
from typos.storage import iter_events

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample-session.jsonl'


def event(key: str, ts: int, mode: str = 'i') -> dict:
    return {'key': key, 'ts_ns': ts, 'mode': mode, 'bufpath': '/x'}


def test_reconstruct_simple_typing() -> None:
    rec = reconstruct([event('h', 1), event('i', 2)])
    assert rec.text == 'hi'
    assert rec.corrections == []


def test_reconstruct_normalizes_space_and_newline() -> None:
    rec = reconstruct(
        [
            event('h', 1),
            event('i', 2),
            event('<Space>', 3),
            event('y', 4),
            event('o', 5),
            event('u', 6),
            event('<CR>', 7),
        ]
    )
    assert rec.text == 'hi you\n'


def test_reconstruct_skips_non_insert_mode() -> None:
    rec = reconstruct(
        [
            event('a', 1, mode='n'),
            event('h', 2),
            event(':', 3, mode='c'),
            event('i', 4),
        ]
    )
    assert rec.text == 'hi'


def test_reconstruct_backspace_emits_correction() -> None:
    rec = reconstruct(
        [
            event('t', 1),
            event('e', 2),
            event('h', 3),
            event('<BS>', 4),
            event('<BS>', 5),
            event('h', 6),
            event('e', 7),
        ]
    )
    assert rec.text == 'the'
    assert len(rec.corrections) == 1
    assert rec.corrections[0].wrong == 'eh'
    assert rec.corrections[0].right == 'he'
    assert rec.corrections[0].start_ts_ns == 4


def test_reconstruct_skips_unknown_special_keys() -> None:
    rec = reconstruct([event('h', 1), event('<C-N>', 2), event('i', 3)])
    assert rec.text == 'hi'


def test_reconstruct_backspace_with_empty_buffer_is_noop() -> None:
    rec = reconstruct([event('<BS>', 1), event('h', 2), event('i', 3)])
    assert rec.text == 'hi'
    assert rec.corrections == []


def test_bigram_stats_counts_ikis() -> None:
    rec = reconstruct(
        [
            event('h', 1_000_000),
            event('e', 2_000_000),
            event('l', 4_000_000),
            event('l', 5_000_000),
            event('o', 9_000_000),
        ]
    )
    stats = bigram_stats(rec.char_timings)
    assert stats['he'].count == 1
    assert stats['he'].ikis_ns == [1_000_000]
    assert stats['lo'].ikis_ns == [4_000_000]
    assert stats['ll'].count == 1


def test_damage_score_is_zero_when_uniform_speed() -> None:
    rec = reconstruct(
        [
            event('a', 0),
            event('b', 1_000_000),
            event('a', 2_000_000),
            event('b', 3_000_000),
        ]
    )
    stats = bigram_stats(rec.char_timings)
    scores = damage_scores(stats)
    for s in scores:
        assert s.score == 0


def test_damage_score_ranks_slow_bigrams_higher() -> None:
    rec = reconstruct(
        [
            event('a', 0),
            event('b', 100_000_000),  # 100ms — slow
            event('c', 110_000_000),
            event('d', 120_000_000),  # cd, dc fast
            event('a', 220_000_000),  # ab again, slow
            event('b', 320_000_000),
        ]
    )
    stats = bigram_stats(rec.char_timings)
    scores = damage_scores(stats)
    assert scores[0].bigram == 'ab'


def test_fixture_smoke() -> None:
    events = list(iter_events(FIXTURE))
    rec = reconstruct(events)
    stats = bigram_stats(rec.char_timings)
    scores = damage_scores(stats)
    assert len(rec.text) > 0
    assert len(stats) > 0
    assert all(s.median_iki_ns > 0 for s in scores)


def test_parse_since_relative() -> None:
    today = date(2026, 4, 26)
    assert parse_since('7d', today=today) == date(2026, 4, 19)
    assert parse_since('30d', today=today) == date(2026, 3, 27)


def test_parse_since_absolute() -> None:
    today = date(2026, 4, 26)
    assert parse_since('2026-04-20', today=today) == date(2026, 4, 20)


def test_parse_since_none() -> None:
    assert parse_since(None) is None


def test_fixture_storage_skips_malformed_bytes() -> None:
    # The fixture contains one line with a vim K_SPECIAL byte (0xfd) that
    # leaked past keytrans before the sanitize_key fix landed. iter_events
    # must be tolerant of this — UTF-8 decode failures are replaced, not raised.
    events = list(iter_events(FIXTURE))
    assert events
