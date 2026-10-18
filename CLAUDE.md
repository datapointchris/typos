# typos

## Purpose

`typos` is a passive typing analyzer. It captures keystrokes while you write real prose in
Neovim (auto-on inside the configured `watch_dirs`, which have no default) and surfaces
patterns: damaging bigrams, mistyped words, typing rhythm consistency over time.

The system is explicitly NOT a typing trainer. It instruments the typing you already do.
Practice generation, when implemented, pulls from real captured patterns and your own
prose corpus — never canned word lists.

## Two layers, and storage is the boundary

The capture layer is `lua/typos/init.lua`: a `vim.on_key()` hook that writes append-only JSONL
while the buffer is under a configured `watch_dirs` entry, overridden per session by `:TyposOn`,
`:TyposOff` and `:TyposAuto`. There is no daemon. The analysis layer is `src/typos/`, where the
CLI consumes the analyzer, the analyzer consumes storage events, and `storage.py` holds no
analysis logic. Storage is the boundary — anything that needs raw events goes through it.

## Storage

- Default: `$XDG_STATE_HOME/typos/sessions/YYYY-MM-DD.jsonl` (fallback `~/.local/state/typos`)
- Override: `TYPOS_DATA_DIR` env var. Both Lua plugin and Python CLI honor it.
- Format: one JSON object per line.

### Event schema

```json
{
  "ts_ns": 12345678900,
  "key": "a",
  "bufpath": "/home/you/writing/2026-04-26.md",
  "mode": "i"
}
```

| Field | Type | Notes |
| ----- | ---- | ----- |
| `ts_ns` | int | Monotonic-since-boot nanoseconds from `vim.uv.hrtime()`. Within-session IKIs only — ts_ns resets each boot, so callers must group by session file before computing intervals. |
| `key` | string | Vim keytrans format. Printables: `"a"`, and a well-formed non-ASCII character such as `"é"` written as itself. Special: `"<Space>"`, `"<BS>"`, `"<CR>"`, `"<Esc>"`, `"<Tab>"`. A byte that is not valid UTF-8, such as a leaked K_SPECIAL code, is written as `<bin:HEX>`. |
| `bufpath` | string | Absolute path of the active buffer. Under one of the configured `watch_dirs` unless `:TyposOn` forced capture on elsewhere; the check happens before write. |
| `mode` | string | The mode string `nvim_get_mode()` returns: `"i"` insert, `"n"` normal, `"v"` visual, `"c"` cmdline, and compound modes such as `"no"` operator-pending and `"nt"` normal in a terminal buffer. Insert-mode events are typing; others are navigation. The analyzer filters to `mode == 'i'`. |

The format is intentionally append-only and additive. Future fields are optional; consumers ignore unknown keys. No version field in v1 — if a breaking change is ever needed, the path becomes `sessions/v2/...` and the analyzer reads both transparently.

What is NOT captured: buffer contents (reconstructable from the keystroke stream), window/tab/split context, modifiers as separate events (already encoded in keytrans output as e.g. `<C-a>`). Mouse clicks are captured, as keys such as `<LeftMouse>` and `<LeftRelease>`, and the analyzer counts none of them as typed.

## Why JSONL not SQLite

Bulk analysis with `jq | sort | uniq -c` is trivial. Incremental analysis with `tail -f`
is trivial. No schema migrations as the analysis evolves. At expected event rates
(~100k/day during heavy writing), the file size stays well within stdlib + pandas/duckdb
territory for years. SQLite would add a query-language layer between the events and the
analyzer for no real gain at this scale.

## Why a session override, not a persisted switch

A persisted "disabled" flag means you can forget you turned capture off and silently lose
weeks of data. A session override means worst case you lose one session, and the next nvim
start goes back to following `watch_dirs`. The asymmetry favors recoverability.

The override is three-state — forced on, forced off, or following `watch_dirs` — which is why
there is no toggle command: over three states a flip has no single obvious meaning.
`:TyposOn` and `:TyposOff` each assert one state, so they are idempotent and safe to bind.

## Why the directory list rather than a mode

Capture answers "am I writing prose", and the buffer path is that question, not a proxy for
it. Reading it per keystroke cannot drift the way a mode set by an autocmd would — no
BufEnter bookkeeping to get wrong across splits, tabs, terminals, or a file moved
mid-session — and it costs one prefix comparison against a list that is almost always one
entry long.

## Why no keyboard detection

The only realistic prose-writing workflow uses one specific external keyboard. Any other case (laptop built-in, etc.) is rare enough that the noise is
acceptable. Detection would require an out-of-band evdev process or a `/dev/input/by-id/`
poll, both of which add platform-specific complexity for marginal gain.

## Damage scoring

Damage is timing alone; no error count enters it. Slowness is misleading on its own: a
bigram that takes three times your usual interval but turns up twice a year costs less than
one a little slow that you hit 200 times a day. The weight (Amphetype-style) is frequency
times relative slowdown:

```text
damage = count × max(0, median − baseline) / median
```

`count` is how often the bigram occurs in the window and `median` is its median interval.
`baseline` is the median interval across every bigram in the window, so the reference is
your own typing rather than a published speed, and a bigram at or under it scores zero.

Reports rank bigrams by damage. Corrections rank words separately, in the mistyped-words
table.

## Anti-features

- No real-time WPM display in statusline. Vanity metric, distracting while writing.
- No dashboards. CLI report is the only UI.
- No canned typing tests. If you want practice mode, use a trainer such as `nvzone/typr`.
- No keyboard layout opinions. The analyzer is layout-agnostic.
