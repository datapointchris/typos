local M = {}

local default_opts = {
  dirs = { "~/notes" },
  data_dir = vim.env.TYPOS_DATA_DIR or "~/shart/typing",
}

local state = {
  opts = nil,
  override = nil,
  ns = nil,
  session_file = nil,
  session_dir_ready = false,
  event_count = 0,
}

-- Capture is on when the current buffer sits under one of `dirs`, and the
-- commands are an override on top of that. Two concerns, deliberately not
-- collapsed: `dirs` says where prose lives, the override says "not right now" or
-- "yes, here too, just this session".
--
-- The override is nil by default and never persisted. A remembered "off" is the
-- one failure this design will not accept — you would forget, and lose weeks of
-- capture silently — so the worst case is losing the session you turned off in.
--
-- Evaluated per keystroke rather than tracked with a BufEnter autocmd: the
-- question "is the thing I am typing into prose" is exactly a property of the
-- current buffer, so reading it directly cannot fall out of step with splits,
-- tabs, terminals, or a file moved mid-session.

-- A bare string is accepted for the single-directory case. Normalised here
-- rather than at the call site so a caller may pass "~/notes" without thinking
-- about expansion, and a trailing slash is stripped because the match below is a
-- prefix test.
local function normalize_dirs(dirs)
  if type(dirs) == "string" then
    dirs = { dirs }
  end
  local normalized = {}
  for _, dir in ipairs(dirs) do
    local expanded = vim.fn.expand(dir):gsub("/+$", "")
    table.insert(normalized, expanded)
  end
  return normalized
end

-- Path only; the directory is created by the first captured keystroke instead.
-- setup() must touch no filesystem, so that a machine configured with dirs it
-- does not have writes nothing and leaves nothing behind.
local function session_file_path()
  return state.opts.data_dir .. "/sessions/" .. os.date("%Y-%m-%d") .. ".jsonl"
end

local function in_configured_dirs(path)
  if not path or path == "" then
    return false
  end
  for _, dir in ipairs(state.opts.dirs) do
    if vim.startswith(path, dir) then
      return true
    end
  end
  return false
end

local function capturing(bufpath)
  if state.override ~= nil then
    return state.override
  end
  return in_configured_dirs(bufpath)
end

local function write_event(event)
  if not state.session_dir_ready then
    vim.fn.mkdir(vim.fs.dirname(state.session_file), "p")
    state.session_dir_ready = true
  end
  local file = io.open(state.session_file, "a")
  if not file then
    return
  end
  file:write(vim.json.encode(event))
  file:write("\n")
  file:close()
  state.event_count = state.event_count + 1
end

-- vim.fn.keytrans handles most special keys but sometimes leaks internal
-- K_SPECIAL escape bytes (0x80-0xfd) for terminal-only key codes. Encode any
-- non-printable byte as <bin:HEX> so the JSONL stays valid UTF-8.
local function sanitize_key(key)
  return (key:gsub("[^\32-\126]", function(c)
    return string.format("<bin:%02x>", string.byte(c))
  end))
end

local function on_key(key, _typed)
  local bufpath = vim.fn.expand("%:p")
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

local function describe_state()
  if state.override == nil then
    return "auto" .. (in_configured_dirs(vim.fn.expand("%:p")) and " (on here)" or " (off here)")
  end
  return state.override and "forced on" or "forced off"
end

function M.setup(opts)
  opts = opts or {}
  state.opts = vim.tbl_deep_extend("force", default_opts, opts)
  -- Assigned after the merge, never through it: a deep extend of two lists
  -- merges them by index, so a shorter configured list would inherit whatever
  -- the default holds past its end.
  state.opts.dirs = normalize_dirs(opts.dirs or default_opts.dirs)
  state.opts.data_dir = vim.fn.expand(state.opts.data_dir)

  state.session_file = session_file_path()
  state.ns = vim.api.nvim_create_namespace("typos")
  vim.on_key(on_key, state.ns)

  -- On and off are separate and idempotent, so a keybind or a script asserts a
  -- state instead of having to read the current one first. There is no toggle:
  -- over three states it would have no single obvious meaning.
  vim.api.nvim_create_user_command("TyposOn", function()
    state.override = true
    vim.notify("typos: capture on everywhere for this session")
  end, { desc = "Capture in every buffer, ignoring the configured dirs" })

  vim.api.nvim_create_user_command("TyposOff", function()
    state.override = false
    vim.notify("typos: capture off for this session")
  end, { desc = "Stop capture everywhere, including the configured dirs" })

  vim.api.nvim_create_user_command("TyposAuto", function()
    state.override = nil
    vim.notify("typos: capture follows " .. table.concat(state.opts.dirs, ", "))
  end, { desc = "Return capture to following the configured dirs" })

  vim.api.nvim_create_user_command("TyposStatus", function()
    vim.notify(
      string.format(
        "typos: %s | dirs=%s | session=%s | events=%d",
        describe_state(),
        table.concat(state.opts.dirs, ", "),
        state.session_file,
        state.event_count
      )
    )
  end, { desc = "Show typos capture state, scope, and event count" })
end

return M
