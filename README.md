# typos

Passive typing analyzer. Captures keystrokes while you write real prose in Neovim and
surfaces patterns you can act on: damaging bigrams, mistyped words, typing rhythm
consistency over time. Practice generation is a secondary feature, derived from the same
data — never from canned word lists.

## Installation

```bash
uv tool install git+https://github.com/datapointchris/typos
```

Then add the Lua plugin to your Neovim config (lazy.nvim example):

```lua
{
  'datapointchris/typos',
  ft = 'markdown',
  cmd = { 'TyposOn', 'TyposOff', 'TyposAuto', 'TyposStatus' },
  opts = {
    watch_dirs = { '~/notes', '~/writing' },
  },
}
```

`watch_dirs` is the auto-on list: capture runs whenever the current buffer sits
under one of them, and stays off everywhere else. There is no default — the plugin
has no idea where your prose lives, so it watches nothing until you say. A single
directory may be given as a bare string, and `~` is expanded for you.

The spec needs no condition guarding it. A machine whose `watch_dirs` are absent
captures nothing, and `setup()` creates no directories either — the session
directory appears with the first captured keystroke.

## Commands

### Neovim

| Command | Purpose |
| ------- | ------- |
| `:TyposOn` | Capture in every buffer this session, ignoring `watch_dirs` |
| `:TyposOff` | Stop capture this session, including inside `watch_dirs` |
| `:TyposAuto` | Return to following `watch_dirs` (the default) |
| `:TyposStatus` | Show capture state, scope, session file path, event count |

`On` and `Off` are a session override on top of `watch_dirs`, so each is idempotent and
a keybind can assert a state without reading the current one first. Neither is
persisted: a remembered "off" is how you lose weeks of capture without noticing,
so the worst case is losing the session you turned off in.

### CLI

| Command | Purpose |
| ------- | ------- |
| `typos status` | Show data location, session count, latest session file |
| `typos report` | Totals, WPM 7d/30d, IKI variance, damaging bigrams, mistyped words, week-over-week deltas |
| `typos problems` | Top mistyped words (`--raw` for raw correction pairs) |
| `typos generate` | Generate practice text from current weak patterns (stub) |

Both `report` and `problems` scope the analysis with `--since` (default `7d`) and `--until`,
each taking `<N>d` or `YYYY-MM-DD`. The window is half-open — `--since` is inclusive, `--until`
is exclusive. `--until` is the frame of reference for everything downstream of it: a relative
`--since` counts back from it, and so do the windows `report` derives for WPM, IKI variance,
and the week-over-week deltas. `--top N` (default 10) controls table length.

## Architecture

Two layers, decoupled by the JSONL event log:

- **Capture** (`lua/typos/init.lua`): Hooks `vim.on_key()`, writes events when the buffer
  path is under one of `watch_dirs`, with a per-session command override. No daemon — the data
  file is the state.
- **Analysis** (`src/typos/`): Python CLI. Reads JSONL, reconstructs correction events,
  computes damage scores, surfaces patterns. Mirrors the three-layer pattern from `relate`:
  `storage.py` → `analyzer.py` → `main.py`.

Storage default: `$XDG_STATE_HOME/typos/sessions/YYYY-MM-DD.jsonl`, falling back to
`~/.local/state/typos`. Override with `TYPOS_DATA_DIR`, which both halves read.

The event schema (`{ts_ns, key, bufpath, mode}` per line) and the damage-score formula
are documented in `CLAUDE.md`.
