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
  dir = '~/code/typos',
  config = function()
    require('typos').setup({
      notes_root = vim.fn.expand('~/notes'),
      data_dir = vim.fn.expand('~/shart/typing'),
    })
  end,
}
```

## Commands

### Neovim

| Command | Purpose |
| ------- | ------- |
| `:TyposToggle` | Enable/disable capture for the current session |
| `:TyposStatus` | Show capture state, session file path, event count |

### CLI

| Command | Purpose |
| ------- | ------- |
| `typos status` | Show data location, session count, last event time |
| `typos report` | Show typing report — WPM, top damaging patterns, longitudinal deltas |
| `typos problems` | Show top damaging bigrams and most-mistyped words |
| `typos generate` | Generate practice text from current weak patterns |

## Architecture

Two layers, decoupled by the JSONL event log:

- **Capture** (`lua/typos/init.lua`): Hooks `vim.on_key()`, writes events when buffer path
  is under `notes_root`. Per-session toggle. No daemon — the data file is the state.
- **Analysis** (`src/typos/`): Python CLI. Reads JSONL, reconstructs correction events,
  computes damage scores, surfaces patterns. Mirrors the three-layer pattern from `relate`:
  `storage.py` → `analyzer.py` → `main.py`.

Storage default: `~/shart/typing/sessions/YYYY-MM-DD.jsonl`. Override with `TYPOS_DATA_DIR`.

See `CLAUDE.md` for design decisions and `.planning/design.md` for the event schema.
