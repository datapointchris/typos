-- Capture-layer tests. Run with `task test:lua`, or directly:
--   nvim --headless -u NONE -l tests/capture_spec.lua
--
-- Plain nvim rather than busted or plenary: the whole surface is vim.on_key, a
-- buffer path and a file write, so driving real nvim tests the thing itself and
-- adds no dependency to a repo whose other half is Python. Exits non-zero on
-- failure so a hook can gate on it.
--
-- These exist because the capture rule is the part with no other safety net. The
-- Python side has pytest over the events; nothing but this notices if the plugin
-- stops writing them, writes them in the wrong place, or writes them everywhere.

local repo_root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
vim.opt.runtimepath:prepend(repo_root)
local typos = require("typos")

local failures = {}
local function check(name, ok)
  if not ok then
    table.insert(failures, name)
  end
  print((ok and "ok   " or "FAIL ") .. name)
end

local tmp = vim.fn.tempname()
local prose = tmp .. "/prose"
local code = tmp .. "/code"
vim.fn.mkdir(prose, "p")
vim.fn.mkdir(code, "p")

local data_dir = tmp .. "/state"
typos.setup({ watch_dirs = { prose }, data_dir = data_dir })

local session = data_dir .. "/sessions/" .. os.date("%Y-%m-%d") .. ".jsonl"

local function events()
  if vim.fn.filereadable(session) == 0 then
    return 0
  end
  return #vim.fn.readfile(session)
end

local function type_into(path, keys)
  vim.cmd("edit " .. path)
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(keys, true, false, true), "x", false)
end

check("setup writes nothing to disk", vim.fn.isdirectory(data_dir) == 0)

for _, cmd in ipairs({ "TyposOn", "TyposOff", "TyposAuto", "TyposStatus" }) do
  check(cmd .. " is defined", vim.fn.exists(":" .. cmd) == 2)
end

type_into(prose .. "/a.md", "ihello<Esc>")
local in_prose = events()
check("a buffer under watch_dirs captures with no command run", in_prose > 0)

type_into(code .. "/b.lua", "iworld<Esc>")
check("a buffer outside watch_dirs captures nothing", events() == in_prose)

-- The recorded path is what the analyzer groups by, so a wrong one is silent.
local first = vim.json.decode(vim.fn.readfile(session)[1])
check("the event records the buffer it came from", first.bufpath == prose .. "/a.md")
check("the event records a mode", type(first.mode) == "string" and first.mode ~= "")

vim.cmd("TyposOn")
type_into(code .. "/c.lua", "iforced<Esc>")
local forced = events()
check("TyposOn overrides watch_dirs and captures anywhere", forced > in_prose)

vim.cmd("TyposOff")
type_into(prose .. "/d.md", "iquiet<Esc>")
check("TyposOff overrides watch_dirs and silences everywhere", events() == forced)

vim.cmd("TyposAuto")
type_into(prose .. "/e.md", "iagain<Esc>")
check("TyposAuto restores the watch_dirs rule", events() > forced)

-- A single directory is the common case; requiring braces for it is a trap.
typos.setup({ watch_dirs = prose .. "/", data_dir = data_dir })
local before_string = events()
type_into(prose .. "/f.md", "istring<Esc>")
check("a bare string watch_dir works, trailing slash included", events() > before_string)

-- The generic default: no watch_dirs means this plugin is inert, which is what
-- lets a consumer install it without a condition guarding the spec.
local unconfigured = tmp .. "/unconfigured"
typos.setup({ data_dir = unconfigured })
type_into(prose .. "/g.md", "inothing<Esc>")
check("no watch_dirs captures nowhere and creates nothing", vim.fn.isdirectory(unconfigured) == 0)

if #failures > 0 then
  print("FAILED: " .. table.concat(failures, ", "))
  vim.cmd("cquit")
end
print("all capture tests passed")
vim.cmd("qall!")
