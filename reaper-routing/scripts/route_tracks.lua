-- Route tracks: record inputs, hardware outs, master send, arm, monitoring and names. Load in REAPER: Actions > Show action list > New action > Load ReaScript.
local TITLE = "Route tracks"
local MONO = 1024

local count = reaper.CountTracks(0)
local o = {
  first = 1, last = count > 0 and count or 64, selected = false, create = true,
  inputs = true, in1 = 1, outs = true, out1 = 1,
  master_off = true, arm = true, mon_off = true,
  names = nil, names_file = nil,
}
local status, prev_down, clicked = "", false, false

local function ask(caption, value)
  local ok, v = reaper.GetUserInputs(TITLE, 1, caption, tostring(value))
  v = ok and tonumber(v)
  if v and v >= 1 then return math.floor(v) end
  return value
end

local function load_names()
  local ok, path = reaper.GetUserFileNameForRead("", "Track names: one per line, line N = track N", "txt")
  if not ok then return end
  local f = io.open(path, "r")
  if not f then
    status = "Can't read " .. path
    return
  end
  local csv = path:lower():match("%.csv$") ~= nil
  local list = {}
  for line in f:lines() do
    line = line:gsub("\r$", "")
    if csv then line = line:match("^([^,]*)") end
    list[#list + 1] = line:match("^%s*(.-)%s*$")
  end
  f:close()
  o.names, o.names_file = list, path:match("[^\\/]+$")
end

local function targets()
  local list = {}
  if o.selected then
    for i = 0, reaper.CountSelectedTracks(0) - 1 do list[#list + 1] = reaper.GetSelectedTrack(0, i) end
    return list
  end
  if o.create then
    while reaper.CountTracks(0) < o.last do reaper.InsertTrackAtIndex(reaper.CountTracks(0), true) end
  end
  for n = o.first, math.min(o.last, reaper.CountTracks(0)) do list[#list + 1] = reaper.GetTrack(0, n - 1) end
  return list
end

local function apply()
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  local list = targets()
  local named = 0
  for k, tr in ipairs(list) do
    if o.inputs then reaper.SetMediaTrackInfo_Value(tr, "I_RECINPUT", o.in1 - 1 + k - 1) end
    if o.outs then
      for s = reaper.GetTrackNumSends(tr, 1) - 1, 0, -1 do reaper.RemoveTrackSend(tr, 1, s) end
      if reaper.CreateTrackSend(tr, nil) >= 0 then
        local idx = reaper.GetTrackNumSends(tr, 1) - 1
        reaper.SetTrackSendInfo_Value(tr, 1, idx, "I_DSTCHAN", o.out1 - 1 + k - 1 + MONO)
        reaper.SetTrackSendInfo_Value(tr, 1, idx, "I_SRCCHAN", MONO)
      end
    end
    if o.master_off then reaper.SetMediaTrackInfo_Value(tr, "B_MAINSEND", 0) end
    if o.arm then reaper.SetMediaTrackInfo_Value(tr, "I_RECARM", 1) end
    if o.mon_off then reaper.SetMediaTrackInfo_Value(tr, "I_RECMON", 0) end
    if o.names then
      local n = math.floor(reaper.GetMediaTrackInfo_Value(tr, "IP_TRACKNUMBER"))
      local name = o.names[n]
      if name and name ~= "" then
        reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true)
        named = named + 1
      end
    end
  end
  reaper.PreventUIRefresh(-1)
  reaper.TrackList_AdjustWindows(false)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("Route tracks", -1)
  status = string.format("Routed %d tracks%s. Ctrl+Z undoes it.", #list,
    o.names and string.format(", named %d", named) or "")
end

local function text(x, y, s, r, g, b)
  gfx.set(r or 0.9, g or 0.9, b or 0.9, 1)
  gfx.x, gfx.y = x, y
  gfx.drawstr(s)
end

local function inside(x, y, w, h)
  return gfx.mouse_x >= x and gfx.mouse_x < x + w and gfx.mouse_y >= y and gfx.mouse_y < y + h
end

local function button(x, y, w, h, label)
  local over = inside(x, y, w, h)
  local c = over and 0.38 or 0.27
  gfx.set(c, c, c, 1)
  gfx.rect(x, y, w, h, 1)
  local tw, th = gfx.measurestr(label)
  text(x + (w - tw) / 2, y + (h - th) / 2, label)
  return over and clicked
end

local function checkbox(x, y, label, value)
  gfx.set(0.8, 0.8, 0.8, 1)
  gfx.rect(x, y, 16, 16, 0)
  if value then
    gfx.set(0.4, 0.75, 1, 1)
    gfx.rect(x + 4, y + 4, 8, 8, 1)
  end
  text(x + 24, y, label)
  local tw = gfx.measurestr(label)
  if inside(x, y, 24 + tw, 18) and clicked then return not value end
  return value
end

local function number(x, y, value, caption)
  if button(x, y - 3, 56, 22, tostring(value)) then return ask(caption, value) end
  return value
end

local function channel_name(get, i)
  local name = get(i)
  return name and name ~= "" and name or tostring(i + 1)
end

local function draw()
  local w, h = gfx.w, gfx.h
  gfx.set(0.13, 0.13, 0.13, 1)
  gfx.rect(0, 0, w, h, 1)
  local n = o.selected and reaper.CountSelectedTracks(0) or (o.last - o.first + 1)
  local y = 16

  o.selected = checkbox(16, y, "Only selected tracks", o.selected)
  y = y + 32
  if o.selected then
    text(16, y, string.format("%d tracks selected", n), 0.7, 0.7, 0.7)
  else
    text(16, y, "Tracks")
    o.first = number(90, y, o.first, "First track")
    text(154, y, "to")
    o.last = math.max(number(180, y, o.last, "Last track"), o.first)
    o.create = checkbox(256, y, "create missing tracks", o.create)
  end

  y = y + 40
  o.inputs = checkbox(16, y, "Record inputs from input", o.inputs)
  o.in1 = number(250, y, o.in1, "First record input")
  if o.inputs and n > 0 then
    local last = o.in1 + n - 1
    text(320, y, string.format("%s ... %s", channel_name(reaper.GetInputChannelName, o.in1 - 1),
      channel_name(reaper.GetInputChannelName, last - 1)), 0.7, 0.7, 0.7)
    if last > reaper.GetNumAudioInputs() then
      text(40, y + 20, string.format("The audio device has %d inputs.", reaper.GetNumAudioInputs()), 1, 0.5, 0.4)
    end
  end

  y = y + 44
  o.outs = checkbox(16, y, "Hardware outs from output", o.outs)
  o.out1 = number(250, y, o.out1, "First hardware output")
  if o.outs and n > 0 then
    local last = o.out1 + n - 1
    text(320, y, string.format("%s ... %s", channel_name(reaper.GetOutputChannelName, o.out1 - 1),
      channel_name(reaper.GetOutputChannelName, last - 1)), 0.7, 0.7, 0.7)
    if last > reaper.GetNumAudioOutputs() then
      text(40, y + 20, string.format("The audio device has %d outputs.", reaper.GetNumAudioOutputs()), 1, 0.5, 0.4)
    end
  end

  y = y + 44
  o.master_off = checkbox(16, y, "Master send off", o.master_off)
  y = y + 28
  o.arm = checkbox(16, y, "Record arm", o.arm)
  y = y + 28
  o.mon_off = checkbox(16, y, "Input monitoring off (no echo to the outs while recording)", o.mon_off)

  y = y + 40
  if button(16, y - 3, 140, 24, o.names and "Other names file" or "Names file...") then load_names() end
  if o.names then
    text(170, y, o.names_file, 0.7, 0.7, 0.7)
    if button(w - 96, y - 3, 80, 24, "No names") then o.names, o.names_file = nil, nil end
  else
    text(170, y, "names unchanged", 0.7, 0.7, 0.7)
  end

  text(16, h - 74, "Unticked options leave the tracks as they are. Hardware outs replace existing ones.", 0.6, 0.6, 0.6)
  text(16, h - 40, status, 0.6, 0.9, 0.6)
  if button(w - 232, h - 46, 100, 30, "Apply") and n > 0 then apply() end
  return button(w - 116, h - 46, 100, 30, "Close")
end

gfx.init(TITLE, 640, 420)
gfx.setfont(1, "Arial", 16)

local function loop()
  local ch = gfx.getchar()
  if ch < 0 or ch == 27 then
    gfx.quit()
    return
  end
  local down = gfx.mouse_cap % 2 == 1
  clicked = prev_down and not down
  prev_down = down
  local close = draw()
  gfx.update()
  if close then
    gfx.quit()
    return
  end
  reaper.defer(loop)
end
loop()
