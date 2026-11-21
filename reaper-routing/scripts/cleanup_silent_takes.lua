-- Remove silent recorded takes, optionally deleting their WAV files. Load in REAPER: Actions > Show action list > New action > Load ReaScript.
local TITLE = "Clean up silent takes"
local BLOCK = 65536
local SLICE = 0.03

local ok, db = reaper.GetUserInputs(TITLE, 1, "Silent below (dBFS)", "-80")
if not ok then return end
db = tonumber(db)
if not db then
  reaper.ShowMessageBox("Enter a level like -80.", TITLE, 0)
  return
end
local limit = 10 ^ (db / 20)

local function file_size(path)
  local f = io.open(path, "rb")
  if not f then return 0 end
  local size = f:seek("end")
  f:close()
  return size or 0
end

local takes = {}
for i = 0, reaper.CountMediaItems(0) - 1 do
  local item = reaper.GetMediaItem(0, i)
  local take = reaper.GetActiveTake(item)
  if take and not reaper.TakeIsMIDI(take) then
    local track = reaper.GetMediaItem_Track(item)
    local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
    takes[#takes + 1] = {
      item = item, take = take, track = track, name = name,
      num = math.floor(reaper.GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER")),
      file = reaper.GetMediaSourceFileName(reaper.GetMediaItemTake_Source(take)),
    }
  end
end
if #takes == 0 then
  reaper.ShowMessageBox("The project has no audio takes.", TITLE, 0)
  return
end

local function finish(t)
  if t.acc then reaper.DestroyAudioAccessor(t.acc) end
  t.acc, t.done = nil, true
end

local function start(t)
  local src = reaper.GetMediaItemTake_Source(t.take)
  t.nch, t.sr = reaper.GetMediaSourceNumChannels(src), reaper.GetMediaSourceSampleRate(src)
  t.started = true
  if t.nch < 1 or t.sr < 1 then
    t.done = true
    return
  end
  t.acc = reaper.CreateTakeAudioAccessor(t.take)
  t.pos, t.stop = reaper.GetAudioAccessorStartTime(t.acc), reaper.GetAudioAccessorEndTime(t.acc)
  t.frames = math.floor(BLOCK / t.nch)
  t.buf = reaper.new_array(t.frames * t.nch)
  t.peak = 0
end

local function step(t)
  if t.pos >= t.stop then
    finish(t)
    return
  end
  local n = math.min(t.frames, math.ceil((t.stop - t.pos) * t.sr))
  if reaper.GetAudioAccessorSamples(t.acc, t.sr, t.nch, t.pos, n, t.buf) < 0 then
    t.peak = nil
    finish(t)
    return
  end
  local s = t.buf.table(1, n * t.nch)
  for i = 1, n * t.nch do
    local v = math.abs(s[i])
    if v > t.peak then
      t.peak = v
      if v > limit then
        finish(t)
        return
      end
    end
  end
  t.pos = t.pos + n / t.sr
end

local state, idx = "scan", 1
local silent, used, bytes = {}, {}, 0
local delete_files, scroll, result = false, 0, {}
local prev_down, clicked = false, false

local function scan()
  local t0 = reaper.time_precise()
  while state == "scan" and reaper.time_precise() - t0 < SLICE do
    local t = takes[idx]
    if not t.started then start(t) end
    if not t.done then step(t) end
    if t.done then
      if t.peak and t.peak <= limit then
        t.size = file_size(t.file)
        bytes = bytes + t.size
        silent[#silent + 1] = t
      else
        used[t.file] = true
      end
      idx = idx + 1
      if idx > #takes then state = "list" end
    end
  end
end

local function remove()
  reaper.Undo_BeginBlock()
  for _, t in ipairs(silent) do reaper.DeleteTrackMediaItem(t.track, t.item) end
  reaper.Undo_EndBlock("Remove silent takes", -1)
  reaper.UpdateArrange()
  if not delete_files then
    result = {
      string.format("Removed %d takes from the project. Ctrl+Z brings them back.", #silent),
      "The WAV files are kept.",
    }
    return
  end
  local removed, failed, freed = 0, 0, 0
  for _, t in ipairs(silent) do
    if not used[t.file] then
      local size = file_size(t.file)
      if os.remove(t.file) then
        removed, freed = removed + 1, freed + size
        os.remove(t.file .. ".reapeaks")
      else
        failed = failed + 1
      end
      used[t.file] = true
    end
  end
  result = {
    string.format("Removed %d takes and deleted %d WAV files, %.0f MB.", #silent, removed, freed / 1048576),
    "Save the project now: undo can't bring deleted audio back.",
  }
  if failed > 0 then
    result[#result + 1] = string.format("%d files could not be deleted (still open).", failed)
    result[#result + 1] = "Save, then use File > Clean current project directory."
  end
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

local function draw()
  local w, h = gfx.w, gfx.h
  gfx.set(0.13, 0.13, 0.13, 1)
  gfx.rect(0, 0, w, h, 1)
  if state == "scan" then
    local t = takes[idx]
    text(16, 16, string.format("Scanning take %d / %d: track %d %s", idx, #takes, t.num, t.name))
    gfx.set(0.3, 0.3, 0.3, 1)
    gfx.rect(16, 48, w - 32, 14, 1)
    gfx.set(0.4, 0.75, 1, 1)
    gfx.rect(16, 48, (w - 32) * (idx - 1) / #takes, 14, 1)
    return button(w - 116, h - 46, 100, 30, "Cancel")
  end
  if state == "done" then
    for i, line in ipairs(result) do text(16, 16 + (i - 1) * 22, line) end
    return button(w - 116, h - 46, 100, 30, "Close")
  end
  if #silent == 0 then
    text(16, 16, string.format("No take is below %g dBFS.", db))
    return button(w - 116, h - 46, 100, 30, "Close")
  end
  text(16, 16, string.format("%d silent takes below %g dBFS, %.0f MB", #silent, db, bytes / 1048576))
  local top, bottom, lh = 48, h - 100, 20
  local rows = math.max(1, math.floor((bottom - top) / lh))
  if gfx.mouse_wheel ~= 0 then
    scroll = scroll - (gfx.mouse_wheel > 0 and 3 or -3)
    gfx.mouse_wheel = 0
  end
  scroll = math.max(0, math.min(scroll, #silent - rows))
  for i = 1, math.min(rows, #silent - scroll) do
    local t = silent[i + scroll]
    local y = top + (i - 1) * lh
    local level = t.peak > 0 and string.format("%.0f dBFS", 20 * math.log(t.peak) / math.log(10)) or "digital silence"
    text(16, y, tostring(t.num))
    text(56, y, t.name)
    text(w - 260, y, level, 0.7, 0.7, 0.7)
    text(w - 100, y, string.format("%.0f MB", t.size / 1048576), 0.7, 0.7, 0.7)
  end
  if #silent > rows then
    text(16, bottom + 4, string.format("scroll for more (%d-%d of %d)", scroll + 1, math.min(scroll + rows, #silent), #silent), 0.6, 0.6, 0.6)
  end
  delete_files = checkbox(16, h - 72, "Also delete the WAV files (can't be undone)", delete_files)
  if button(w - 232, h - 46, 100, 30, "Remove") then
    remove()
    state = "done"
    return false
  end
  return button(w - 116, h - 46, 100, 30, "Cancel")
end

local function cleanup()
  local t = takes[idx]
  if t and t.acc then finish(t) end
end
reaper.atexit(cleanup)

gfx.init(TITLE, 620, 520)
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
  if state == "scan" then scan() end
  local close = draw()
  gfx.update()
  if close then
    gfx.quit()
    return
  end
  reaper.defer(loop)
end
loop()
