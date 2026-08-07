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
  cmd = { 'TyposToggle', 'TyposStatus' },
  opts = {
    notes_root = vim.fn.expand('~/notes'),
    data_dir = vim.fn.expand('~/shart/typing'),
  },
}
```

The spec needs no condition guarding it. Capture is scoped to `notes_root`, so on
a machine without one the `vim.on_key` hook matches no buffer and writes nothing,
and `setup()` creates no directories — the data directory appears on the first
captured keystroke.

## Commands

### Neovim

| Command | Purpose |
| ------- | ------- |
| `:TyposToggle` | Enable/disable capture for the current session |
| `:TyposStatus` | Show capture state, session file path, event count |

### CLI

| Command | Purpose |
| ------- | ------- |
| `typos status` | Show data location, session count, latest session file |
| `typos report` | Totals, WPM 7d/30d, IKI variance, damaging bigrams, mistyped words, week-over-week deltas |
| `typos problems` | Top mistyped words (`--raw` for raw correction pairs) |
| `typos generate` | Generate practice text from current weak patterns (stub) |

Both `report` and `problems` accept `--since 7d` (default) or `--since YYYY-MM-DD` to scope
the window, and `--top N` (default 10) to control table length.

## Architecture

Two layers, decoupled by the JSONL event log:

- **Capture** (`lua/typos/init.lua`): Hooks `vim.on_key()`, writes events when buffer path
  is under `notes_root`. Per-session toggle. No daemon — the data file is the state.
- **Analysis** (`src/typos/`): Python CLI. Reads JSONL, reconstructs correction events,
  computes damage scores, surfaces patterns. Mirrors the three-layer pattern from `relate`:
  `storage.py` → `analyzer.py` → `main.py`.

Storage default: `~/shart/typing/sessions/YYYY-MM-DD.jsonl`. Override with `TYPOS_DATA_DIR`.

The event schema (`{ts_ns, key, bufpath, mode}` per line) and the damage-score formula
are documented in `CLAUDE.md`.
