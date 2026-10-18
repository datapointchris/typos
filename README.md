# typos

A passive typing analyzer for prose written in Neovim. A Lua plugin records each keystroke you make
in the directories you write in. A Python CLI reads that log back as patterns worth acting on: the
bigrams costing you the most time, the words you correct most often, and how steady your rhythm is
from one week to the next.

It instruments the typing you already do and sets no exercises. A trainer such as `nvzone/typr` is
the neighbor: typos finds the patterns, and the trainer drills them. It is unrelated to the
source-code spell checker that holds the name `typos` on PyPI.

## Install

```bash
uv tool install --index https://pypi.ichrisbirch.com/simple/ typos   # the CLI, from its own index
task install                                                          # or from a checkout, editable
```

Every release is published to that package index. Name it on the install, because PyPI's `typos`
is that spell checker. Both put a `typos` executable on `PATH`, and whichever comes first there
answers. uv records the index beside the tool, so `uv tool upgrade typos` reads it back.

The plugin needs Neovim 0.10 or later, the first release with `vim.uv`. With lazy.nvim:

```lua
{
  'datapointchris/typos',
  ft = 'markdown',
  cmd = { 'TyposOn', 'TyposOff', 'TyposAuto', 'TyposStatus' },
  opts = {
    watch_dirs = { '~/writing', '~/journal' },
  },
}
```

`watch_dirs` is the auto-on list. Capture runs in any buffer under one of them, and stays off
everywhere else, a sibling such as `~/writing-old` included. A single directory may be a bare string. `~` is expanded, and a trailing
slash is dropped.

`ft` decides only when the plugin loads. Capture follows the buffer's path and ignores its filetype,
so prose kept in anything but markdown wants `event = 'VeryLazy'` in place of `ft`.

## Starting from scratch

```bash
uv tool install --index https://pypi.ichrisbirch.com/simple/ typos  # the CLI
# add the spec above to your Neovim config, with watch_dirs naming where you write
nvim ~/writing/first-draft.md   # type a few lines; the first key creates the log
:TyposStatus                    # inside Neovim: auto (on here), and events above 0
typos status                    # the data dir the CLI reads; latest is today's file
typos report                    # your keys back, counted and timed
```

`watch_dirs` has no default, since any default would be one person's layout shipped as everyone's.
Until it is set, the plugin captures nothing. `setup()` creates nothing on disk either, so the spec
needs no guard on a machine where those directories are absent. The session directory appears with
the first captured keystroke.

When `:TyposStatus` counts events and `typos status` says `sessions: 0`, the two halves are reading
different directories. Each resolves the path from its own environment: `TYPOS_DATA_DIR` first, then
`$XDG_STATE_HOME/typos`, then `~/.local/state/typos`. The plugin also takes a `data_dir` option, and
the CLI never reads it. Move the log with the environment variable rather than the option.

## The `:Typos` commands — a session override on top of `watch_dirs`, never a saved switch

```vim
:TyposStatus   " state, watch_dirs, the session file, events written since the plugin loaded
:TyposOn       " capture in every buffer this session, watch_dirs or not
:TyposOff      " capture nowhere this session, watch_dirs included
:TyposAuto     " follow watch_dirs again, which is where every session starts
```

The override has three states: forced on, forced off, and following `watch_dirs`. A toggle over three
states has no single obvious meaning, so there is none. `:TyposOn` and `:TyposOff` each assert one
state. Both are idempotent, so a keybind can set a state without reading the current one.

Nothing is persisted. A remembered "off" is how weeks of capture disappear without anyone noticing.
A session override loses at most the session it was set in, and the next start follows `watch_dirs`
again.

`:TyposOn` means every buffer. No buffer type is checked, so a terminal buffer's keystrokes are
logged too.

Capture is decided on each keystroke from the current buffer's path. The question is "am I writing
prose", and the path answers it directly. A mode set by an autocmd could fall out of step across
splits, tabs, terminals, or a file moved mid-session. Reading the path costs one prefix comparison
per watched directory.

## `typos` — bigrams ranked by the time they cost, not by how often they go wrong

```bash
typos status               # where the CLI reads, how many day files, and the latest
typos report               # the weekly read: totals, WPM, rhythm, damaging bigrams, mistyped words
typos report --since 30d   # the same read over a month
typos problems --raw       # the deleted and retyped keys behind a word the report flagged
```

`report` ranks bigrams by damage:

```text
damage = count × max(0, median − baseline) / median
```

`count` is how often the bigram occurs in the window. `median` is its median interval between the
two keys. `baseline` is your own median interval across every bigram. A bigram typed at or under
your baseline scores zero. Frequency carries the weight, so a slightly slow bigram you type all day
outranks a very slow one you type twice a year.

A correction is a run of backspaces in insert mode and whatever was typed after it, credited to the
word being typed. `problems` ranks words by their corrections. `--raw` counts corrections instead
as pairs of the keys deleted and the keys retyped.

WPM counts active time only. A gap of five seconds or more between keys is a pause and is left out,
and five characters count as a word. IKI variance is the spread of the intervals between keys over
the last seven days, set beside the seven before. A lower number is a steadier rhythm. The report
closes on the bigrams whose damage moved more than 20% week over week.

`--since` is inclusive and `--until` is exclusive. `--until` is the frame of reference: a relative
`--since` counts back from it, and so does every window `report` derives for WPM, variance and the
weekly deltas. `--since 7d --until 2026-07-01` reads 24 June through 30 June. With no `--until`,
every window runs through today and holds exactly the days it names, so `--since 7d` is the last
seven days with today included.

## The log — append-only JSONL, and the only thing the two halves share

There is no daemon. The plugin appends one JSON object per keystroke to
`$XDG_STATE_HOME/typos/sessions/YYYY-MM-DD.jsonl`, falling back to `~/.local/state/typos`, and the
CLI reads the same files. `TYPOS_DATA_DIR` overrides the location for both. A file is named for the
day Neovim loaded the plugin, so a session that runs past midnight stays in the day it began.

```json
{"ts_ns": 758059084204886, "key": "T", "bufpath": "/home/you/writing/draft.md", "mode": "i"}
```

- `ts_ns` is `vim.uv.hrtime()`, nanoseconds on a clock that restarts at boot. It measures the
  intervals between keys, never the time of day.
- `key` is in Neovim's `keytrans` notation: `a`, `<Space>`, `<BS>`, `<CR>`, `<C-a>`. A modifier is
  part of the key, never an event of its own. A character outside ASCII, such as `é`, is written
  as itself and counts as typed. A byte that is not valid UTF-8, such as an internal key code
  leaking past `keytrans`, is written as `<bin:HEX>`, so the line stays valid UTF-8.
- `bufpath` is the buffer's absolute path.
- `mode` is Neovim's mode string. Only `i` is typing. The analyzer reads insert-mode events, and any
  other event ends the correction in progress.

Readers ignore keys they do not know, so a field can be added without breaking an older analyzer.

The log holds no buffer contents and no window, tab or split. The keystrokes still reconstruct what
you typed, which is how the analyzer finds words, so the log is as private as the prose.

The analysis side runs in one direction. `storage.py` reads the files, `analyzer.py` turns events
into statistics, and `main.py` prints them. Storage holds no analysis, and nothing reads the files
except through it.

The log is JSONL rather than SQLite because both kinds of analysis stay one command. Bulk analysis
is a `jq` pipeline, and incremental analysis is `tail -f`. Both lines read the default location,
and `typos status` prints yours:

```bash
jq -r 'select(.mode == "i") | .key' ~/.local/state/typos/sessions/*.jsonl | sort | uniq -c | sort -rn | head
tail -f ~/.local/state/typos/sessions/"$(date +%F)".jsonl   # keys as they arrive
```

No schema has to migrate as the analysis changes. SQLite would add a query layer between the events
and the analyzer, and buy nothing at keystroke volume.

## No dashboard, no live WPM, no keyboard detection

- No live WPM in the statusline. It is a vanity metric, and it distracts while writing.
- No dashboard. The CLI report is the only interface.
- No canned typing tests. Drilling belongs to a trainer.
- No keyboard-layout opinions. The analyzer treats keys as keys, whatever the layout.
- No keyboard detection. Keys from a second keyboard are noise the analysis accepts, because
  detecting the device needs an out-of-band evdev process or a `/dev/input/by-id/` poll. That is
  platform-specific machinery for a marginal gain.
