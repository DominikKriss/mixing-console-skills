local MONO = 1024

local function options(o)
  local base = { first = 1, last = 4, selected = false, create = true, inputs = true, in1 = 1, outs = true, out1 = 1,
    master_off = true, arm = true, mon_off = true }
  for k, v in pairs(o or {}) do base[k] = v end
  return base
end

test("route: creates missing tracks and routes 1:1", function()
  local M, P = load_script("route_tracks.lua")
  P.add_track("A")
  local status, count = M.apply(options())
  eq(count, 4, "tracks routed")
  eq(#P.tracks, 4, "tracks in project")
  for n, t in ipairs(P.tracks) do
    eq(t.info.I_RECINPUT, n - 1, "input of track " .. n)
    eq(#t.hw, 1, "hardware outs of track " .. n)
    eq(t.hw[1].I_DSTCHAN, n - 1 + MONO, "output of track " .. n)
    eq(t.hw[1].I_SRCCHAN, MONO, "source of track " .. n)
    eq(t.info.B_MAINSEND, 0, "master send")
    eq(t.info.I_RECARM, 1, "armed")
    eq(t.info.I_RECMON, 0, "monitoring")
  end
  truthy(status:find("Routed 4 tracks", 1, true), "status")
  eq(P.undo, 0, "undo block closed")
end)

test("route: offsets and range", function()
  local M, P = load_script("route_tracks.lua")
  for i = 1, 6 do P.add_track() end
  M.apply(options({ first = 3, last = 4, in1 = 17, out1 = 33 }))
  eq(P.tracks[3].info.I_RECINPUT, 16, "track 3 input")
  eq(P.tracks[4].hw[1].I_DSTCHAN, 33 + MONO, "track 4 output")
  eq(#P.tracks[1].hw, 0, "track 1 untouched")
  eq(P.tracks[1].info.B_MAINSEND, 1, "track 1 master untouched")
end)

test("route: existing hardware outs are replaced by exactly one", function()
  local M, P = load_script("route_tracks.lua")
  local t = P.add_track()
  t.hw = { { I_DSTCHAN = 5 }, { I_DSTCHAN = 6 } }
  M.apply(options({ last = 1 }))
  eq(#t.hw, 1, "hardware outs")
  eq(t.hw[1].I_DSTCHAN, MONO, "new output")
end)

test("route: a failed hardware out keeps the old routing", function()
  local M, P = load_script("route_tracks.lua")
  local t = P.add_track()
  t.hw = { { I_DSTCHAN = 5 } }
  P.send_fail = true
  local status, _, failed = M.apply(options({ last = 1 }))
  eq(failed, 1, "failures")
  eq(#t.hw, 1, "old outs kept")
  eq(t.hw[1].I_DSTCHAN, 5, "old output unchanged")
  truthy(status:find("kept their old hardware outs", 1, true), "status")
end)

test("route: unticked options leave tracks alone", function()
  local M, P = load_script("route_tracks.lua")
  local t = P.add_track()
  t.info.I_RECINPUT, t.hw = 7, { { I_DSTCHAN = 9 } }
  M.apply(options({ last = 1, inputs = false, outs = false, master_off = false, arm = false, mon_off = false }))
  eq(t.info.I_RECINPUT, 7, "input")
  eq(t.hw[1].I_DSTCHAN, 9, "output")
  eq(t.info.B_MAINSEND, 1, "master")
  eq(t.info.I_RECARM, 0, "arm")
  eq(t.info.I_RECMON, 1, "monitoring")
end)

test("route: selected tracks only, counted in order", function()
  local M, P = load_script("route_tracks.lua")
  for i = 1, 4 do P.add_track() end
  P.tracks[2].selected, P.tracks[4].selected = true, true
  M.apply(options({ selected = true, in1 = 10 }))
  eq(P.tracks[2].info.I_RECINPUT, 9, "first selected")
  eq(P.tracks[4].info.I_RECINPUT, 10, "second selected")
  eq(P.tracks[1].info.I_RECARM, 0, "unselected untouched")
end)

test("route: names go to track N, blank lines keep the name", function()
  local M, P = load_script("route_tracks.lua")
  P.add_track("old1")
  P.add_track("old2")
  M.apply(options({ last = 2, names = { "", "KICK" } }))
  eq(P.tracks[1].name, "old1", "blank keeps")
  eq(P.tracks[2].name, "KICK", "named")
end)

test("route: first CSV field", function()
  local M = load_script("route_tracks.lua")
  eq(M.first_csv_field("KICK,1"), "KICK", "plain")
  eq(M.first_csv_field('"Keys, lead",2'), "Keys, lead", "quoted comma")
  eq(M.first_csv_field('"Input "", left",unused'), 'Input ", left', "escaped quote")
  eq(M.first_csv_field('  "OH"'), "OH", "quoted only")
  eq(M.first_csv_field(""), "", "empty")
end)

test("route: save and load names round trip with gaps", function()
  local M, P = load_script("route_tracks.lua")
  P.add_track("KICK")
  P.add_track("")
  P.add_track("OH L")
  local path = temp_file("")
  local good, named, count = M.write_names(path)
  truthy(good, "write")
  eq(named, 2, "named")
  eq(count, 3, "tracks")
  local list = M.read_names(path)
  eq(#list, 3, "lines")
  eq(list[1], "KICK", "line 1")
  eq(list[2], "", "line 2")
  eq(list[3], "OH L", "line 3")
end)

test("route: names are always saved as .txt", function()
  local M = load_script("route_tracks.lua")
  eq(M.txt_path("a/names.csv"), "a/names.txt", "csv")
  eq(M.txt_path("names"), "names.txt", "no extension")
  eq(M.txt_path("names.TXT"), "names.TXT", "txt kept")
end)

test("route: a failing write reports the error", function()
  local M, P = load_script("route_tracks.lua")
  P.add_track("KICK")
  M.open = function() return nil, "read-only", 30 end
  local good, err = M.write_names("x.txt")
  eq(good, false, "result")
  eq(err, "read-only", "error")
  M.open = function()
    return { write = function() return nil, "disk full" end, close = function() return true end }
  end
  eq((M.write_names("y.txt")), false, "write failure")
  M.open = function()
    return { write = function(self) return self end, close = function() return nil, "close failed" end }
  end
  local ok2, err2 = M.write_names("z.txt")
  eq(ok2, false, "close failure")
  eq(err2, "close failed", "close error")
end)
