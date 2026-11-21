-- In-memory stand-in for the REAPER API calls the ReaScripts use. Synthetic data only.
local Mock = {}

function Mock.new()
  local P = { proj = { id = "project" }, projfn = "", tracks = {}, items = {}, change = 0, reads = 0,
    open_accessors = 0, send_fail = false, undo = 0 }
  P.current = P.proj

  function P.add_track(name)
    local t = { name = name or "", info = { I_RECINPUT = 0, I_RECARM = 0, I_RECMON = 1, B_MAINSEND = 1 }, hw = {} }
    P.tracks[#P.tracks + 1] = t
    return t
  end

  function P.source(o)
    o = o or {}
    return { file = o.file or "", samples = o.samples or {}, nch = o.nch or 1, sr = o.sr or 100, parent = o.parent }
  end

  function P.take(src, midi)
    return { src = src, midi = midi }
  end

  function P.add_item(track, takes, active, pos)
    local item = { track = track, takes = takes, active = active or 1, pos = pos or 0 }
    for _, tk in ipairs(takes) do tk.item = item end
    P.items[#P.items + 1] = item
    return item
  end

  local function index_of(list, v)
    for i, x in ipairs(list) do if x == v then return i end end
  end

  local function new_array(size)
    local a = { data = {}, size = size }
    a.table = function(off, n)
      local t = {}
      for i = 1, n do t[i] = a.data[off + i - 1] or 0 end
      return t
    end
    a.clear = function() a.data = {} end
    return a
  end

  local r = {}
  r.EnumProjects = function() return P.current, P.projfn end
  r.GetProjectStateChangeCount = function() return P.change end
  r.GetProjectName = function() return P.projname or "" end
  r.ValidatePtr2 = function(proj, ptr, kind)
    if proj ~= P.proj or kind ~= "MediaItem_Take*" then return false end
    return ptr.item ~= nil and index_of(P.items, ptr.item) ~= nil
  end
  r.time_precise = os.clock

  r.CountMediaItems = function() return #P.items end
  r.GetMediaItem = function(_, i) return P.items[i + 1] end
  r.GetActiveTake = function(item) return item.takes[item.active] end
  r.CountTakes = function(item) return #item.takes end
  r.GetTake = function(item, k) return item.takes[k + 1] end
  r.TakeIsMIDI = function(take) return take.midi == true end
  r.GetMediaItem_Track = function(item) return item.track end
  r.GetMediaItemInfo_Value = function(item, key) if key == "D_POSITION" then return item.pos end end
  r.DeleteTrackMediaItem = function(_, item)
    local i = index_of(P.items, item)
    if not i then return false end
    table.remove(P.items, i)
    P.change = P.change + 1
    return true
  end
  r.format_timestr = function(t) return string.format("%.3f", t) end

  r.GetMediaItemTake_Source = function(take) return take.src end
  r.GetMediaSourceParent = function(src) return src.parent end
  r.GetMediaSourceFileName = function(src) return src.file end
  r.GetMediaSourceNumChannels = function(src) return src.nch end
  r.GetMediaSourceSampleRate = function(src) return src.sr end

  r.new_array = new_array
  r.CreateTakeAudioAccessor = function(take)
    P.open_accessors = P.open_accessors + 1
    return { src = take.src }
  end
  r.DestroyAudioAccessor = function(acc)
    if not acc.closed then P.open_accessors = P.open_accessors - 1 end
    acc.closed = true
  end
  r.GetAudioAccessorStartTime = function() return 0 end
  r.GetAudioAccessorEndTime = function(acc) return #acc.src.samples / acc.src.nch / acc.src.sr end
  r.GetAudioAccessorSamples = function(acc, sr, nch, t, n, buf)
    if acc.src.read_error then return -1 end
    P.reads = P.reads + 1
    if P.on_read then P.on_read() end
    local first = math.floor(t * sr + 0.5) * nch
    buf.data = {}
    for i = 1, n * nch do buf.data[i] = acc.src.samples[first + i] or 0 end
    return 1
  end

  r.CountTracks = function() return #P.tracks end
  r.GetTrack = function(_, i) return P.tracks[i + 1] end
  r.InsertTrackAtIndex = function(idx)
    local t = { name = "", info = { I_RECINPUT = 0, I_RECARM = 0, I_RECMON = 1, B_MAINSEND = 1 }, hw = {} }
    table.insert(P.tracks, idx + 1, t)
  end
  r.CountSelectedTracks = function()
    local n = 0
    for _, t in ipairs(P.tracks) do if t.selected then n = n + 1 end end
    return n
  end
  r.GetSelectedTrack = function(_, i)
    local n = -1
    for _, t in ipairs(P.tracks) do
      if t.selected then
        n = n + 1
        if n == i then return t end
      end
    end
  end
  r.GetMediaTrackInfo_Value = function(tr, key)
    if key == "IP_TRACKNUMBER" then return index_of(P.tracks, tr) or 0 end
    return tr.info[key]
  end
  r.SetMediaTrackInfo_Value = function(tr, key, value)
    tr.info[key] = value
    return true
  end
  r.GetSetMediaTrackInfo_String = function(tr, key, value, set)
    if key ~= "P_NAME" then return false, "" end
    if set then tr.name = value end
    return true, tr.name
  end
  r.GetTrackNumSends = function(tr, category) return category > 0 and #tr.hw or 0 end
  r.CreateTrackSend = function(tr, dest)
    if dest ~= nil or P.send_fail then return -1 end
    tr.hw[#tr.hw + 1] = { I_DSTCHAN = 0, I_SRCCHAN = 0 }
    return #tr.hw - 1
  end
  r.RemoveTrackSend = function(tr, category, idx)
    if category <= 0 or not tr.hw[idx + 1] then return false end
    table.remove(tr.hw, idx + 1)
    return true
  end
  r.SetTrackSendInfo_Value = function(tr, category, idx, key, value)
    if category <= 0 or not tr.hw[idx + 1] then return false end
    tr.hw[idx + 1][key] = value
    return true
  end

  r.Undo_BeginBlock = function() P.undo = P.undo + 1 end
  r.Undo_EndBlock = function() P.undo = P.undo - 1 end
  r.UpdateArrange = function() end
  r.PreventUIRefresh = function() end
  r.TrackList_AdjustWindows = function() end

  return r, P
end

return Mock
