from __future__ import annotations

from datetime import date
from pathlib import Path

from typos.analyzer import DamageScore
from typos.analyzer import bigram_stats
from typos.analyzer import compute_iki_variance
from typos.analyzer import compute_wpm
from typos.analyzer import damage_deltas
from typos.analyzer import damage_scores
from typos.analyzer import mistyped_words
from typos.analyzer import parse_since
from typos.analyzer import reconstruct
from typos.analyzer import session_wpm_components
from typos.analyzer import trailing_word
from typos.analyzer import variance_ns_to_ms
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


def test_session_wpm_components_excludes_idle_gaps() -> None:
    # 5 chars, IKIs: 100ms, 100ms, 6_000ms (idle), 100ms.
    # Idle gap drops out, leaving 300ms total active time.
    events = [
        event('a', 0),
        event('b', 100_000_000),
        event('c', 200_000_000),
        event('d', 6_200_000_000),
        event('e', 6_300_000_000),
    ]
    chars, active_ns = session_wpm_components(events)
    assert chars == 5
    assert active_ns == 300_000_000


def test_session_wpm_components_short_buffer() -> None:
    chars, active_ns = session_wpm_components([event('a', 0)])
    assert chars == 1
    assert active_ns == 0


def test_compute_wpm_aggregates_across_sessions() -> None:
    # Two sessions, each 5 chars over 1 second of active time.
    # Total: 10 chars / 5 chars-per-word = 2 words; 2 seconds = 1/30 minute.
    # WPM = 2 / (1/30) = 60.
    session_a = [event('a', i * 250_000_000) for i in range(5)]
    session_b = [event('b', i * 250_000_000) for i in range(5)]
    wpm = compute_wpm([session_a, session_b])
    assert wpm == 60.0


def test_compute_wpm_zero_with_no_active_time() -> None:
    assert compute_wpm([[event('a', 0)]]) == 0.0
    assert compute_wpm([]) == 0.0


def test_compute_iki_variance_zero_with_uniform_speed() -> None:
    events = [event('a', i * 100_000_000) for i in range(10)]
    assert compute_iki_variance([events]) == 0.0


def test_compute_iki_variance_excludes_idle_gaps() -> None:
    events = [event('x', 0)]
    for i in range(4):
        events.append(event('a', (i + 1) * 100_000_000))
    events.append(event('b', 10_500_000_000))
    for i in range(4):
        events.append(event('c', 10_500_000_000 + (i + 1) * 100_000_000))
    assert compute_iki_variance([events]) == 0.0


def test_compute_iki_variance_aggregates_across_sessions() -> None:
    session_a = [event('a', i * 100_000_000) for i in range(5)]
    session_b = [event('b', i * 200_000_000) for i in range(5)]
    variance = compute_iki_variance([session_a, session_b])
    assert variance > 0


def test_variance_ns_to_ms_conversion() -> None:
    assert variance_ns_to_ms(1_000_000_000_000) == 1.0
    assert variance_ns_to_ms(0) == 0.0


def test_trailing_word_extracts_to_whitespace() -> None:
    buf = [(c, i) for i, c in enumerate('the cat sat')]
    assert trailing_word(buf) == 'sat'
    assert trailing_word([(c, i) for i, c in enumerate('hello\nworld')]) == 'world'
    assert trailing_word([(c, i) for i, c in enumerate('foo\tbar')]) == 'bar'
    assert trailing_word([]) == ''
    assert trailing_word([(c, i) for i, c in enumerate('one ')]) == ''


def test_correction_records_word_context() -> None:
    rec = reconstruct(
        [
            event('t', 1),
            event('h', 2),
            event('e', 3),
            event('<Space>', 4),
            event('c', 5),
            event('a', 6),
            event('y', 7),
            event('<BS>', 8),
            event('t', 9),
        ]
    )
    assert rec.text == 'the cat'
    assert len(rec.corrections) == 1
    assert rec.corrections[0].word_context == 'cat'


def test_mistyped_words_aggregates_by_word_context() -> None:
    rec = reconstruct(
        [
            event('t', 1),
            event('h', 2),
            event('e', 3),
            event('<Space>', 4),
            event('c', 5),
            event('a', 6),
            event('y', 7),
            event('<BS>', 8),
            event('t', 9),
            event('<Space>', 10),
            event('s', 11),
            event('a', 12),
            event('y', 13),
            event('<BS>', 14),
            event('t', 15),
        ]
    )
    words = mistyped_words(rec.text, rec.corrections)
    assert {w.word for w in words} == {'cat', 'sat'}
    cat = next(w for w in words if w.word == 'cat')
    assert cat.typed == 1
    assert cat.corrections == 1
    assert cat.rate == 1.0


def make_score(bigram: str, score: float) -> DamageScore:
    return DamageScore(bigram=bigram, count=10, median_iki_ns=300_000_000, score=score)


def test_damage_deltas_classifies_improvements_and_regressions() -> None:
    prior = [make_score('ab', 8.0), make_score('cd', 2.0), make_score('ef', 5.0)]
    current = [make_score('ab', 4.0), make_score('cd', 8.0), make_score('ef', 5.1)]
    improved, worsened = damage_deltas(prior, current)
    assert {d.bigram for d in improved} == {'ab'}
    assert {d.bigram for d in worsened} == {'cd'}


def test_damage_deltas_threshold_filters_small_changes() -> None:
    prior = [make_score('ab', 5.0)]
    current = [make_score('ab', 5.05)]
    improved, worsened = damage_deltas(prior, current, threshold=0.2)
    assert not improved
    assert not worsened


def test_damage_deltas_skips_bigrams_only_in_one_window() -> None:
    prior = [make_score('ab', 5.0)]
    current = [make_score('cd', 8.0)]
    improved, worsened = damage_deltas(prior, current)
    assert not improved
    assert not worsened


def test_damage_deltas_sort_orders_by_magnitude() -> None:
    prior = [make_score('ab', 10.0), make_score('cd', 10.0), make_score('ef', 10.0)]
    current = [make_score('ab', 1.0), make_score('cd', 5.0), make_score('ef', 8.0)]
    improved, _ = damage_deltas(prior, current)
    assert [d.bigram for d in improved] == ['ab', 'cd']


def test_mistyped_words_typed_counts_word_in_final_text() -> None:
    rec = reconstruct(
        [
            event('t', 1),
            event('e', 2),
            event('<BS>', 3),
            event('h', 4),
            event('e', 5),
            event('<Space>', 6),
            event('t', 7),
            event('h', 8),
            event('e', 9),
        ]
    )
    words = mistyped_words(rec.text, rec.corrections)
    the = next(w for w in words if w.word == 'the')
    assert the.typed == 2
    assert the.corrections == 1
    assert the.rate == 0.5


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
