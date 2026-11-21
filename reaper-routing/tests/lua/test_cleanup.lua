local SILENT = { 0, 0, 0, 0 }
local QUIET = { 0.00001, -0.00002, 0.00001, 0 }
local LOUD = { 0, 0.5, -0.4, 0 }

local function setup()
  local M, P = load_script("cleanup_silent_takes.lua")
  return M, P, P.add_track("T1")
end

local function item(P, track, samples, file, opts)
  opts = opts or {}
  local src = P.source({ file = file or temp_file(), samples = samples, parent = opts.parent })
  return P.add_item(track, { P.take(src) }, 1, opts.pos)
end

local function scan(M, db)
  local ctx = M.collect(db or -80)
  M.scan(ctx)
  return ctx
end

test("cleanup: silent and quiet takes are candidates, loud ones are not", function()
  local M, P, tr = setup()
  item(P, tr, SILENT)
  item(P, tr, QUIET)
  item(P, tr, LOUD)
  local ctx = scan(M)
  eq(ctx.state, "list", "state")
  eq(#ctx.silent, 2, "silent takes")
  eq(ctx.silent[1].peak, 0, "digital silence peak")
  eq(P.open_accessors, 0, "accessors left open")
end)

test("cleanup: threshold decides", function()
  local M, P, tr = setup()
  item(P, tr, QUIET)
  eq(#scan(M, -120).silent, 0, "quiet take above -120 dBFS")
end)

test("cleanup: remove deletes only ticked items and keeps files by default", function()
  local M, P, tr = setup()
  local a = item(P, tr, SILENT)
  local b = item(P, tr, SILENT)
  local loud = item(P, tr, LOUD)
  local ctx = scan(M)
  ctx.silent[2].selected = false
  M.remove(ctx, false)
  eq(ctx.state, "done", "state")
  eq(#P.items, 2, "items left")
  eq(P.items[1], b, "unticked item kept")
  eq(P.items[2], loud, "loud item kept")
  truthy(exists(a.takes[1].src.file), "file of removed item kept without the checkbox")
  eq(P.undo, 0, "undo block closed")
end)

test("cleanup: item with a silent active take and an audible inactive take is skipped", function()
  local M, P, tr = setup()
  local silent = P.take(P.source({ file = temp_file(), samples = SILENT }))
  local loud = P.take(P.source({ file = temp_file(), samples = LOUD }))
  local multi = P.add_item(tr, { silent, loud }, 1)
  local single = item(P, tr, SILENT)
  local ctx = scan(M)
  eq(ctx.multi, 1, "multi-take items counted")
  eq(#ctx.silent, 1, "only the single-take item is a candidate")
  M.remove(ctx, true)
  eq(#P.items, 1, "items left")
  eq(P.items[1], multi, "multi-take item kept")
  truthy(exists(silent.src.file) and exists(loud.src.file), "multi-take files kept")
  truthy(not exists(single.takes[1].src.file), "single-take silent file deleted")
  truthy(M.skipped_note(ctx):find("1 items with several takes skipped", 1, true), "note")
end)

test("cleanup: a file another take still uses is not deleted", function()
  local M, P, tr = setup()
  local shared = temp_file()
  item(P, tr, SILENT, shared)
  local inactive = P.take(P.source({ file = shared, samples = SILENT }))
  local other = P.take(P.source({ file = temp_file(), samples = LOUD }))
  P.add_item(tr, { other, inactive }, 1)
  local own = item(P, tr, SILENT)
  local ctx = scan(M)
  eq(#ctx.silent, 2, "candidates")
  M.remove(ctx, true)
  truthy(exists(shared), "shared file kept")
  truthy(not exists(own.takes[1].src.file), "own file deleted")
end)

test("cleanup: section takes resolve to the parent file", function()
  local M, P, tr = setup()
  local wav = temp_file()
  local parent = P.source({ file = wav, samples = LOUD })
  P.add_item(tr, { P.take(P.source({ file = "", samples = LOUD, parent = parent })) }, 1)
  item(P, tr, SILENT, wav)
  local ctx = scan(M)
  eq(#ctx.silent, 1, "candidates")
  M.remove(ctx, true)
  truthy(exists(wav), "file used by the section take kept")
end)

test("cleanup: missing file is listed as offline, removed, not deleted", function()
  local M, P, tr = setup()
  local gone = missing_path()
  item(P, tr, LOUD, gone)
  local removed = {}
  M.remove_file = function(p) removed[#removed + 1] = p return true end
  local ctx = scan(M)
  eq(#ctx.silent, 1, "offline take listed")
  truthy(ctx.silent[1].missing, "marked missing")
  eq(P.reads, 0, "no audio read for a missing file")
  M.remove(ctx, true)
  eq(#P.items, 0, "offline item removed")
  eq(#removed, 0, "nothing deleted")
end)

test("cleanup: a file that can't be read is skipped, not treated as missing", function()
  local M, P, tr = setup()
  local locked = temp_file()
  item(P, tr, LOUD, locked)
  local real = M.open
  M.open = function(path, mode)
    if path == locked then return nil, locked .. ": Permission denied", 13 end
    return real(path, mode)
  end
  local ctx = scan(M)
  eq(#ctx.takes, 0, "takes to scan")
  eq(ctx.unreadable, 1, "unreadable counted")
  truthy(M.skipped_note(ctx):find("can't be read", 1, true), "note")
end)

test("cleanup: a take deleted during the scan is skipped", function()
  local M, P, tr = setup()
  item(P, tr, SILENT)
  local victim = item(P, tr, SILENT)
  item(P, tr, SILENT)
  local ctx = M.collect(-80)
  table.remove(P.items, 2)
  M.scan(ctx)
  eq(ctx.state, "list", "state")
  eq(#ctx.silent, 2, "deleted take not listed")
  for _, t in ipairs(ctx.silent) do truthy(t.item ~= victim, "victim not a candidate") end
  eq(P.open_accessors, 0, "accessors left open")
end)

test("cleanup: switching project during the scan stops it", function()
  local M, P, tr = setup()
  item(P, tr, SILENT)
  item(P, tr, SILENT)
  local ctx = M.collect(-80)
  M.scan(ctx, 0)
  eq(ctx.idx, 2, "one take scanned in the first step")
  P.current = { id = "other" }
  M.scan(ctx)
  eq(ctx.state, "done", "state")
  truthy(ctx.result[1]:find("Another project", 1, true), "message")
  eq(P.open_accessors, 0, "accessors left open")
end)

test("cleanup: a project change after the scan blocks Remove", function()
  local M, P, tr = setup()
  item(P, tr, SILENT)
  local ctx = scan(M)
  P.change = P.change + 1
  M.remove(ctx, true)
  eq(#P.items, 1, "nothing removed")
  truthy(ctx.result[1]:find("changed after the scan", 1, true), "message")
end)

test("cleanup: read errors keep the take", function()
  local M, P, tr = setup()
  local it = item(P, tr, SILENT)
  it.takes[1].src.read_error = true
  eq(#scan(M).silent, 0, "take with a read error not listed")
end)

test("cleanup: every scan step makes progress", function()
  local M, P, tr = setup()
  for _ = 1, 3 do item(P, tr, SILENT) end
  local ctx = M.collect(-80)
  local steps = 0
  while ctx.state == "scan" and steps < 10 do
    M.scan(ctx, 0)
    steps = steps + 1
  end
  eq(ctx.state, "list", "state")
  eq(steps, 3, "one take per zero-budget step")
end)

test("cleanup: MIDI takes are ignored", function()
  local M, P, tr = setup()
  P.add_item(tr, { P.take(P.source({ samples = SILENT }), true) }, 1)
  local ctx = M.collect(-80)
  eq(#ctx.takes, 0, "takes")
  eq(ctx.state, "list", "state with nothing to scan")
end)
