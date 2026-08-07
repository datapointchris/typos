local M = {}

local default_opts = {
  notes_root = vim.fn.expand("~/notes"),
  data_dir = vim.env.TYPOS_DATA_DIR and vim.fn.expand(vim.env.TYPOS_DATA_DIR) or vim.fn.expand("~/shart/typing"),
  enabled = true,
}

local state = {
  opts = nil,
  enabled = true,
  ns = nil,
  session_file = nil,
  session_dir_ready = false,
  event_count = 0,
}

-- Path only; the directory is created by the first captured keystroke instead.
-- setup() must touch no filesystem: capture is scoped to notes_root, so on a
-- machine that does not have one this plugin writes nothing at all, and creating
-- a data directory there would leave a Syncthing-shaped tree on a machine that
-- syncs nothing.
local function session_file_path()
  return state.opts.data_dir .. "/sessions/" .. os.date("%Y-%m-%d") .. ".jsonl"
end

local function in_notes_root(path)
  if not path or path == "" then
    return false
  end
  return vim.startswith(path, state.opts.notes_root)
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
  if not state.enabled then
    return
  end
  local bufpath = vim.fn.expand("%:p")
  if not in_notes_root(bufpath) then
    return
  end
  write_event({
    ts_ns = vim.uv.hrtime(),
    key = sanitize_key(vim.fn.keytrans(key)),
    bufpath = bufpath,
    mode = vim.api.nvim_get_mode().mode,
  })
end

function M.setup(opts)
  state.opts = vim.tbl_deep_extend("force", default_opts, opts or {})
  state.enabled = state.opts.enabled
  state.session_file = session_file_path()
  state.ns = vim.api.nvim_create_namespace("typos")
  vim.on_key(on_key, state.ns)

  vim.api.nvim_create_user_command("TyposToggle", function()
    state.enabled = not state.enabled
    vim.notify("typos: " .. (state.enabled and "enabled" or "disabled"))
  end, { desc = "Toggle typos capture for this session" })

  vim.api.nvim_create_user_command("TyposStatus", function()
    vim.notify(
      string.format(
        "typos: %s | session=%s | events=%d",
        state.enabled and "enabled" or "disabled",
        state.session_file,
        state.event_count
      )
    )
  end, { desc = "Show typos capture status" })
end

return M
