-- Runs the ReaScript tests against mock_reaper.lua: lua tests/lua/run.lua (from the skill folder or anywhere).
local here = (arg and arg[0] or ""):match("^(.*)[/\\]") or "."
package.path = here .. "/?.lua;" .. package.path
local Mock = require("mock_reaper")

SCRIPTS = here .. "/../../scripts/"
local tests, failures = {}, 0

function test(name, fn) tests[#tests + 1] = { name = name, fn = fn } end

function eq(actual, expected, what)
  if actual ~= expected then
    error(string.format("%s: expected %s, got %s", what or "value", tostring(expected), tostring(actual)), 2)
  end
end

function truthy(v, what)
  if not v then error((what or "condition") .. " is false", 2) end
end

local temp = {}
function temp_file(content)
  local path = os.tmpname()
  local f = assert(io.open(path, "wb"))
  f:write(content or "RIFF")
  f:close()
  temp[#temp + 1] = path
  return path
end

function missing_path()
  local path = os.tmpname()
  os.remove(path)
  return path .. "_missing.wav"
end

function exists(path)
  local f = io.open(path, "rb")
  if f then f:close() end
  return f ~= nil
end

function load_script(name)
  local r, P = Mock.new()
  reaper = r
  REAPER_ROUTING_TEST = true
  local M = dofile(SCRIPTS .. name)
  return M, P
end

for _, file in ipairs({ "test_cleanup.lua", "test_route_tracks.lua" }) do dofile(here .. "/" .. file) end

for _, t in ipairs(tests) do
  local ok, err = pcall(t.fn)
  if ok then
    print("ok   " .. t.name)
  else
    failures = failures + 1
    print("FAIL " .. t.name .. "\n     " .. tostring(err))
  end
end
for _, path in ipairs(temp) do os.remove(path) end
print(string.format("%d tests, %d failed", #tests, failures))
os.exit(failures == 0 and 0 or 1)
