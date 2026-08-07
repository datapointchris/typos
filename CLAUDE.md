# typos

## Purpose

`typos` is a passive typing analyzer. It captures keystrokes while you write real prose in
Neovim (auto-on inside the configured `dirs`, `~/notes/` by default) and surfaces patterns:
damaging bigrams, mistyped words, typing rhythm consistency over time.

The system is explicitly NOT a typing trainer. It instruments the typing you already do.
Practice generation, when implemented, pulls from real captured patterns and your own
prose corpus — never canned word lists.

## Two-Layer Architecture

```yaml
lua/typos/init.lua    Capture layer. vim.on_key() hook, on while the buffer is under
                      one of the configured `dirs`. Writes append-only JSONL. Session
                      override via :TyposOn / :TyposOff / :TyposAuto. No daemon.

src/typos/storage.py  Pure JSONL I/O. Append events, iterate sessions. No analysis logic.
src/typos/analyzer.py Correction-event reconstruction, damage scoring, longitudinal stats.
src/typos/main.py     Typer CLI. Thin commands consuming analyzer.py.
src/typos/config.py   Paths, env var overrides, defaults.
```

CLI commands consume analyzer outputs. Analyzer consumes storage events. Storage is the
boundary — anything that needs raw events goes through it.

## Storage

- Default: `~/shart/typing/sessions/YYYY-MM-DD.jsonl`
- Override: `TYPOS_DATA_DIR` env var. Both Lua plugin and Python CLI honor it.
- Format: one JSON object per line.

### Event schema

```json
{
  "ts_ns": 12345678900,
  "key": "a",
  "bufpath": "/home/chris/notes/dreams/2026-04-26.md",
  "mode": "i"
}
```

| Field | Type | Notes |
| ----- | ---- | ----- |
| `ts_ns` | int | Monotonic-since-boot nanoseconds from `vim.uv.hrtime()`. Within-session IKIs only — ts_ns resets each boot, so callers must group by session file before computing intervals. |
| `key` | string | Vim keytrans format. Printables: `"a"`, `" "`. Special: `"<BS>"`, `"<CR>"`, `"<Esc>"`, `"<Tab>"`. Internal K_SPECIAL bytes are sanitized to `<bin:HEX>` at write. |
| `bufpath` | string | Absolute path of the active buffer. Under one of the configured `dirs` unless `:TyposOn` forced capture on elsewhere; the check happens before write. |
| `mode` | string | `"i"` insert, `"n"` normal, `"v"` visual, `"c"` cmdline. Insert-mode events are typing; others are navigation. The analyzer filters to `mode == 'i'`. |

The format is intentionally append-only and additive. Future fields are optional; consumers ignore unknown keys. No version field in v1 — if a breaking change is ever needed, the path becomes `sessions/v2/...` and the analyzer reads both transparently.

What is NOT captured: buffer contents (reconstructable from the keystroke stream), window/tab/split context, mouse events, modifiers as separate events (already encoded in keytrans output as e.g. `<C-a>`).

## Why JSONL not SQLite

Bulk analysis with `jq | sort | uniq -c` is trivial. Incremental analysis with `tail -f`
is trivial. No schema migrations as the analysis evolves. At expected event rates
(~100k/day during heavy writing), the file size stays well within stdlib + pandas/duckdb
territory for years. SQLite would add a query-language layer between the events and the
analyzer for no real gain at this scale.

## Why a session override, not a persisted switch

A persisted "disabled" flag means you can forget you turned capture off and silently lose
weeks of data. A session override means worst case you lose one session, and the next nvim
start goes back to following `dirs`. The asymmetry favors recoverability.

The override is three-state — forced on, forced off, or following `dirs` — which is why
there is no toggle command: over three states a flip has no single obvious meaning.
`:TyposOn` and `:TyposOff` each assert one state, so they are idempotent and safe to bind.

## Why the directory list rather than a mode

Capture answers "am I writing prose", and the buffer path is that question, not a proxy for
it. Reading it per keystroke cannot drift the way a mode set by an autocmd would — no
BufEnter bookkeeping to get wrong across splits, tabs, terminals, or a file moved
mid-session — and it costs one prefix comparison against a list that is almost always one
entry long.

## Why no keyboard detection

The user's only realistic typing-into-`~/notes` workflow uses one specific external
keyboard. Any other case (laptop built-in, etc.) is rare enough that the noise is
acceptable. Detection would require an out-of-band evdev process or a `/dev/input/by-id/`
poll, both of which add platform-specific complexity for marginal gain.

## Damage scoring

The "most mistyped" framing is misleading on its own. A bigram you mistype 50% of the
time but only see twice a year matters less than a bigram you mistype 5% of the time but
hit 200x/day. The right weight (Amphetype-style):

```text
damage = frequency_in_corpus × max(0, your_time - reference_time) / your_time
```

Reports rank by damage, not raw error count.

## Anti-features

- No real-time WPM display in statusline. Vanity metric, distracting while writing.
- No dashboards. CLI report is the only UI.
- No canned typing tests. If you want practice mode, use `nvzone/typr` and feed it text
  generated by `typos generate`.
- No keyboard layout opinions. The analyzer is layout-agnostic.
