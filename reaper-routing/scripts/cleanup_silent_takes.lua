-- Remove silent recorded takes and their WAV files. Run from REAPER: Actions > Show action list > New action > Load ReaScript.
local BLOCK = 65536

local function file_size(path)
  local f = io.open(path, "rb")
  if not f then return 0 end
  local size = f:seek("end")
  f:close()
  return size or 0
end

local function peak(take, limit)
  local src = reaper.GetMediaItemTake_Source(take)
  local nch = reaper.GetMediaSourceNumChannels(src)
  local sr = reaper.GetMediaSourceSampleRate(src)
  if nch < 1 or sr < 1 then return nil end
  local acc = reaper.CreateTakeAudioAccessor(take)
  local t, stop = reaper.GetAudioAccessorStartTime(acc), reaper.GetAudioAccessorEndTime(acc)
  local frames = math.floor(BLOCK / nch)
  local buf = reaper.new_array(frames * nch)
  local max = 0
  while t < stop do
    local n = math.min(frames, math.ceil((stop - t) * sr))
    buf.clear()
    if reaper.GetAudioAccessorSamples(acc, sr, nch, t, n, buf) < 0 then
      reaper.DestroyAudioAccessor(acc)
      return nil
    end
    local s = buf.table(1, n * nch)
    for i = 1, n * nch do
      local v = math.abs(s[i])
      if v > max then
        max = v
        if max > limit then
          reaper.DestroyAudioAccessor(acc)
          return max
        end
      end
    end
    t = t + n / sr
  end
  reaper.DestroyAudioAccessor(acc)
  return max
end

local ok, csv = reaper.GetUserInputs("Clean up silent takes", 2,
  "Silent below (dBFS),Delete WAV files (y/n)", "-80,y")
if not ok then return end
local db, del = csv:match("^%s*([%-%d%.]+)%s*,%s*([yYnN])")
if not db then
  reaper.ShowMessageBox("Enter a level like -80 and y or n.", "Clean up silent takes", 0)
  return
end
local limit = 10 ^ (tonumber(db) / 20)
del = del:lower() == "y"

local silent, used, lines, bytes = {}, {}, {}, 0
for i = 0, reaper.CountMediaItems(0) - 1 do
  local item = reaper.GetMediaItem(0, i)
  local take = reaper.GetActiveTake(item)
  if take and not reaper.TakeIsMIDI(take) then
    local file = reaper.GetMediaSourceFileName(reaper.GetMediaItemTake_Source(take))
    local p = peak(take, limit)
    if p and p <= limit then
      local track = reaper.GetMediaItem_Track(item)
      local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
      local num = math.floor(reaper.GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER"))
      silent[#silent + 1] = { item = item, track = track, file = file }
      local size = file_size(file)
      bytes = bytes + size
      local level = p > 0 and string.format("%.0f dBFS", 20 * math.log(p) / math.log(10)) or "digital silence"
      lines[#lines + 1] = string.format("%3d %-16s %s, %.0f MB", num, name, level, size / 1048576)
    else
      used[file] = true
    end
  end
end

if #silent == 0 then
  reaper.ShowMessageBox("No take is below " .. db .. " dBFS.", "Clean up silent takes", 0)
  return
end

local shown = {}
for i = 1, math.min(#lines, 40) do shown[i] = lines[i] end
if #lines > 40 then shown[#shown + 1] = string.format("... and %d more", #lines - 40) end
local msg = string.format("%d silent takes, %.0f MB:\n\n%s\n\nRemove them from the project%s?",
  #silent, bytes / 1048576, table.concat(shown, "\n"), del and " and delete their WAV files" or "")
if reaper.ShowMessageBox(msg, "Clean up silent takes", 4) ~= 6 then return end

reaper.Undo_BeginBlock()
for _, s in ipairs(silent) do reaper.DeleteTrackMediaItem(s.track, s.item) end
reaper.Undo_EndBlock("Remove silent takes", -1)
reaper.UpdateArrange()

if not del then return end
local removed, failed, freed = 0, {}, 0
for _, s in ipairs(silent) do
  if not used[s.file] then
    local size = file_size(s.file)
    if os.remove(s.file) then
      removed, freed = removed + 1, freed + size
      os.remove(s.file .. ".reapeaks")
    else
      failed[#failed + 1] = s.file
    end
    used[s.file] = true
  end
end
local report = string.format("Deleted %d WAV files, %.0f MB.\nSave the project now: the removed takes are gone from disk, so undo can't bring their audio back.",
  removed, freed / 1048576)
if #failed > 0 then
  report = report .. string.format("\n\n%d files could not be deleted (still open). Save, then use File > Clean current project directory.", #failed)
end
reaper.ShowMessageBox(report, "Clean up silent takes", 0)
