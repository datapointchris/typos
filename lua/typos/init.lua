local M = {}

-- Captured sessions are state, not data: they survive across runs, no human
-- authored them, and deleting one changes what the analyzer reports rather than
-- costing a recompute. src/typos/config.py resolves this identically — the two
-- halves have to agree on the path without either knowing the other's machine.
local function default_data_dir()
  if vim.env.TYPOS_DATA_DIR and vim.env.TYPOS_DATA_DIR ~= '' then
    return vim.env.TYPOS_DATA_DIR
  end
  if vim.env.XDG_STATE_HOME and vim.env.XDG_STATE_HOME ~= '' then
    return vim.env.XDG_STATE_HOME .. '/typos'
  end
  return '~/.local/state/typos'
end

-- watch_dirs is empty on purpose. This plugin knows nothing about whose machine
-- it is on, so it watches nothing until a config says where that person's prose
-- lives; a default like "~/notes" would be one user's layout shipped as though
-- it were everyone's.
local default_opts = {
  watch_dirs = {},
  data_dir = default_data_dir(),
}

local state = {
  opts = nil,
  override = nil,
  ns = nil,
  session_file = nil,
  session_dir_ready = false,
  event_count = 0,
}

-- Capture is on when the current buffer sits under one of `watch_dirs`, and the
-- commands are an override on top of that. Two concerns, deliberately not
-- collapsed: `watch_dirs` says where prose lives, the override says "not right
-- now" or "yes, here too, just this session".
--
-- The override is nil by default and never persisted. A remembered "off" is the
-- one failure this design will not accept — you would forget, and lose weeks of
-- capture silently — so the worst case is losing the session you turned off in.
--
-- Evaluated per keystroke rather than tracked with a BufEnter autocmd: the
-- question "is the thing I am typing into prose" is exactly a property of the
-- current buffer, so reading it directly cannot fall out of step with splits,
-- tabs, terminals, or a file moved mid-session.

-- A bare string is accepted for the single-directory case. Normalized here
-- rather than at the call site so a caller may pass "~/writing" without thinking
-- about expansion, and a trailing slash is stripped so the match below can add
-- exactly one separator of its own.
local function normalize_dirs(dirs)
  if type(dirs) == 'string' then
    dirs = { dirs }
  end
  local normalized = {}
  for _, dir in ipairs(dirs) do
    local expanded = vim.fn.expand(dir):gsub('/+$', '')
    table.insert(normalized, expanded)
  end
  return normalized
end

-- Path only; the directory is created by the first captured keystroke instead.
-- setup() must touch no filesystem, so that a machine whose watch_dirs are absent
-- writes nothing and leaves nothing behind.
local function session_file_path()
  return state.opts.data_dir .. '/sessions/' .. os.date('%Y-%m-%d') .. '.jsonl'
end

-- Matched on a directory boundary, so `~/writing` never claims `~/writing-old`.
local function in_watch_dirs(path)
  if not path or path == '' then
    return false
  end
  for _, dir in ipairs(state.opts.watch_dirs) do
    if path == dir or vim.startswith(path, dir .. '/') then
      return true
    end
  end
  return false
end

local function capturing(bufpath)
  if state.override ~= nil then
    return state.override
  end
  return in_watch_dirs(bufpath)
end

local function write_event(event)
  if not state.session_dir_ready then
    vim.fn.mkdir(vim.fs.dirname(state.session_file), 'p')
    state.session_dir_ready = true
  end
  local file = io.open(state.session_file, 'a')
  if not file then
    return
  end
  file:write(vim.json.encode(event))
  file:write('\n')
  file:close()
  state.event_count = state.event_count + 1
end

-- The length of the well-formed UTF-8 sequence starting at byte i, or nil when
-- there is none. The ranges are Unicode's table of well-formed byte sequences,
-- so an overlong form, a surrogate and a stray continuation byte are all refused.
local function utf8_length(s, i)
  local lead = s:byte(i)
  if lead < 0x80 then
    return 1
  end
  local length, low, high
  if lead >= 0xc2 and lead <= 0xdf then
    length, low, high = 2, 0x80, 0xbf
  elseif lead == 0xe0 then
    length, low, high = 3, 0xa0, 0xbf
  elseif lead == 0xed then
    length, low, high = 3, 0x80, 0x9f
  elseif lead >= 0xe1 and lead <= 0xef then
    length, low, high = 3, 0x80, 0xbf
  elseif lead == 0xf0 then
    length, low, high = 4, 0x90, 0xbf
  elseif lead >= 0xf1 and lead <= 0xf3 then
    length, low, high = 4, 0x80, 0xbf
  elseif lead == 0xf4 then
    length, low, high = 4, 0x80, 0x8f
  else
    return nil
  end
  local second = s:byte(i + 1)
  if not second or second < low or second > high then
    return nil
  end
  for j = i + 2, i + length - 1 do
    local continuation = s:byte(j)
    if not continuation or continuation < 0x80 or continuation > 0xbf then
      return nil
    end
  end
  return length
end

-- vim.fn.keytrans handles most special keys but sometimes leaks internal
-- K_SPECIAL escape bytes for terminal-only key codes. Those bytes are not valid
-- UTF-8, so each one is written as <bin:HEX> and the JSONL stays valid UTF-8. A
-- well-formed character such as é is written as itself, so it counts as typed.
local function sanitize_key(key)
  local parts = {}
  local i = 1
  while i <= #key do
    local length = utf8_length(key, i)
    if length then
      table.insert(parts, key:sub(i, i + length - 1))
      i = i + length
    else
      table.insert(parts, string.format('<bin:%02x>', key:byte(i)))
      i = i + 1
    end
  end
  return table.concat(parts)
end

local function on_key(key, _typed)
  local bufpath = vim.fn.expand('%:p')
  if not capturing(bufpath) then
    return
  end
  write_event({
    ts_ns = vim.uv.hrtime(),
    key = sanitize_key(vim.fn.keytrans(key)),
    bufpath = bufpath,
    mode = vim.api.nvim_get_mode().mode,
  })
end

local function describe_scope()
  if #state.opts.watch_dirs == 0 then
    return 'none configured'
  end
  return table.concat(state.opts.watch_dirs, ', ')
end

local function describe_state()
  if state.override ~= nil then
    return state.override and 'forced on' or 'forced off'
  end
  if #state.opts.watch_dirs == 0 then
    return 'auto (no watch_dirs, so off everywhere)'
  end
  return 'auto' .. (in_watch_dirs(vim.fn.expand('%:p')) and ' (on here)' or ' (off here)')
end

function M.setup(opts)
  opts = opts or {}
  state.opts = vim.tbl_deep_extend('force', default_opts, opts)
  -- Assigned after the merge, never through it: a deep extend of two lists
  -- merges them by index, so a shorter configured list would inherit whatever
  -- the default holds past its end.
  state.opts.watch_dirs = normalize_dirs(opts.watch_dirs or default_opts.watch_dirs)
  state.opts.data_dir = vim.fn.expand(state.opts.data_dir)

  state.session_file = session_file_path()
  state.ns = vim.api.nvim_create_namespace('typos')
  vim.on_key(on_key, state.ns)

  -- On and off are separate and idempotent, so a keybind or a script asserts a
  -- state instead of having to read the current one first. There is no toggle:
  -- over three states it would have no single obvious meaning.
  vim.api.nvim_create_user_command('TyposOn', function()
    state.override = true
    vim.notify('typos: capture on everywhere for this session')
  end, { desc = 'Capture in every buffer, ignoring watch_dirs' })

  vim.api.nvim_create_user_command('TyposOff', function()
    state.override = false
    vim.notify('typos: capture off for this session')
  end, { desc = 'Stop capture everywhere, including inside watch_dirs' })

  vim.api.nvim_create_user_command('TyposAuto', function()
    state.override = nil
    vim.notify('typos: capture follows ' .. describe_scope())
  end, { desc = 'Return capture to following watch_dirs' })

  vim.api.nvim_create_user_command('TyposStatus', function()
    vim.notify(
      string.format(
        'typos: %s | watch_dirs=%s | session=%s | events=%d',
        describe_state(),
        describe_scope(),
        state.session_file,
        state.event_count
      )
    )
  end, { desc = 'Show typos capture state, scope, and event count' })
end

return M
