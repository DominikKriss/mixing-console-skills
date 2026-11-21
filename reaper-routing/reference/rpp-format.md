# REAPER project (.rpp): track routing fields

A `.rpp` is a text file of nested `<CHUNK ... >` blocks, one attribute per line, CRLF on Windows saves. Tracks
are `<TRACK {GUID}` chunks directly under `<REAPER_PROJECT`; their own attributes are at that depth, and nested
chunks (`<ITEM`, `<FXCHAIN`, envelopes) carry their own `NAME` and other lines, which the script never touches.

Sources: [ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html) (track and send attributes, read
2026-11-21 from the v7.86 page) and a REAPER 7.35 / Windows project with 64 recorded tracks where hardware outs 1
and 2 were set by hand on tracks 1 and 2.

| Line | Fields the script uses | Proof |
|---|---|---|
| `NAME ""` | track name, quoted. | Project save (empty names written as `""`). Quoting a name with `'` or `` ` `` when it contains `"` is **unconfirmed**. |
| `REC 1 0 1 0 0 0 0 0` | 1st: armed (`I_RECARM`). 2nd: input (`I_RECINPUT`): mono input N = `N-1`; `+1024` = stereo pair from N; `<0` none; 4096 = MIDI. 3rd: monitoring (`I_RECMON`: 0 off, 1 normal, 2 not when playing). | Project save: 64 armed tracks with inputs 0-63 for inputs 1-64, monitoring 1. Encoding from the API. Stereo and the monitoring position **unconfirmed** in a save. |
| `MAINSEND 1 0` | 1st: send to master / parent (`B_MAINSEND`). 2nd: parent channel offset. | Project save (`1 0` on every track); `0` = off from the API, **unconfirmed** in a save. |
| `HWOUT 1024 0 1 0 0 0 0 -1:U -1` | one line per hardware out, after `MAINSEND`. 1st: destination (`I_DSTCHAN`), low 10 bits = output index from 0, `+1024` = mix to mono. 2nd: send mode (`I_SENDMODE`, 0 post-fader). 3rd: volume (1.0 = 0 dB). 7th: source (`I_SRCCHAN`), offset in the low 10 bits, `(src>>10)` 0 = stereo pair, 1 = mono. Other fields are copied as REAPER wrote them. | Project save: `1024` / `1025` = mono out 1 / 2 with source `0` (channels 1/2), set by hand. Mono source `1024` and stereo destination **unconfirmed** in a save. |

## Open

- One project for recording and playback: armed tracks with monitoring off play their items to the hardware outs
  when not recording. Confirm in REAPER.
- Load a script-written project in REAPER and confirm in the routing matrix: names, master send off, mono source
  `1024` (channel 1 only) and stereo pairs. Record the REAPER version and date in the README status.
- Whether a mono source from channel 1 plays a centred mono item at the recorded level (the hand-set `0` source
  mixes channels 1/2 to mono, which depends on the pan law).

## LV1 patch to a DAW device (`--device`)

Read from an LV1 17.3 `.emo` (tables `device`, `device_name`, `device_daw`, `routes`); consistent for three devices
in one session, **unconfirmed** by a controlled save.

- SoundGrid devices are in `device`; `device_gender` 1 = DAW (driver) device. Its display name is
  `device_name.name` (joined on `mac` and gender), the computer's hostname is `device_daw.hostname`.
- In `routes`, a device is addressed by `io_bank * 8 + assign`: `src_cluster_type` 10 (Inputs) for what it sends,
  `dst_cluster_type` 11 (Outputs) for what it receives. `src_channel_index` / `dst_channel_index` are 0-based
  channels.
- Device input → LV1 input: `dst_cluster_type` 0, `dst_cluster_type_index` = LV1 input from 0,
  `dst_channel_index` 0 = left / mono, 1 = right of a stereo input.
- Recording patch: rows with `dst_cluster_type` 11 and the DAW device's index, source a device input channel
  (direct I/O, not a channel direct out). The script names a recording channel after the lowest LV1 input fed by
  the same device channel.

## Cleanup ReaScript (`scripts/cleanup_silent_takes.lua`)

Runs inside REAPER. API calls, all from the [ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html)
(v7.86 page, read 2026-11-21): `GetUserInputs`, `CountMediaItems`, `GetMediaItem`, `GetActiveTake`, `TakeIsMIDI`,
`GetMediaItemTake_Source`, `GetMediaSourceFileName`, `GetMediaSourceNumChannels`, `GetMediaSourceSampleRate`,
`CreateTakeAudioAccessor`, `GetAudioAccessorStartTime`, `GetAudioAccessorEndTime`, `GetAudioAccessorSamples`
(interleaved, pre-FX; returns -1 on error), `DestroyAudioAccessor`, `new_array` (`.clear`, `.table` with 1-based
offsets), `GetMediaItem_Track`, `GetSetMediaTrackInfo_String` (`P_NAME`), `GetMediaTrackInfo_Value`
(`IP_TRACKNUMBER`), `ShowMessageBox` (type 4 = Yes/No, 6 = Yes), `Undo_BeginBlock`, `Undo_EndBlock`,
`DeleteTrackMediaItem`, `UpdateArrange`.

- A take is silent when its peak over the item (pre-FX, so track volume and FX don't matter) is at or below the
  threshold (default -80 dBFS). Scanning stops at the first sample above it, so tracks with audio are quick.
- A file is deleted only when no remaining item uses it. Windows refuses to delete a file REAPER still has open;
  the script then names REAPER's File > Clean current project directory, whose action ID isn't documented, so the
  script doesn't call it.
- The Lua version isn't documented, so the script avoids `math.log(x, base)`.
- **Unconfirmed:** not yet run in REAPER.
