# reaper-routing

Route a REAPER project for live multitrack recording and virtual soundcheck without clicking through 64 tracks:
record inputs, hardware outputs (1:1, offset, stereo pairs), master send, track names from the console show
(LV1 `.emo`, X32 `.scn`, WING `.snap`, text list), record arm and monitoring, plus a REAPER action that deletes
silent takes after a recording. See [SKILL.md](SKILL.md) for the
commands and [reference/rpp-format.md](reference/rpp-format.md) for the format.

## Status

- Script tested on a REAPER 7.35 / Windows 64-track project (2026-11-21): only the intended lines change, CRLF kept.
- `route_tracks.lua` (routing window): run in REAPER on Windows (2026-11-21/22): routing, names, Save names, replacing hardware outs.
- `cleanup_silent_takes.lua`: run in REAPER on Windows (2026-11-21/22): lists silent and offline takes, per-row selection, removes them, deletes the WAVs only with the checkbox, survives an item deleted mid-scan. Multi-take items: mock test only.
- REAPER load of a script-written project: **not yet confirmed** (see `reference/rpp-format.md`, Open).

## Tests

From the `reaper-routing` folder:

```sh
python3 -m unittest discover -s tests -t tests
lua tests/lua/run.lua
```

(`run.lua` locates its files from its own path, so `lua reaper-routing/tests/lua/run.lua` works from the
repository root too.)

The ReaScripts run against `tests/lua/mock_reaper.lua`, an in-memory stand-in for the REAPER calls they use; the
unittest run includes them when Lua (5.4 or later) is installed, and CI requires it on Linux.
