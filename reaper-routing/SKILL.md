---
name: reaper-routing
description: >-
  Route a REAPER project (.rpp) for live multitrack recording and virtual soundcheck by script: record inputs and
  hardware outputs for every track from range maps (1:1 or offset, mono or stereo pairs), master send on / off,
  track names from the console show (Waves LV1 .emo, Behringer X32 .scn, WING .snap, or a text list), record arm
  and monitoring in one project, and a ReaScript that deletes silent takes after a recording. Use when the user asks to route,
  patch, name or set up REAPER tracks / inputs / outputs, prepare a multitrack recording or virtual soundcheck,
  says routing 32 / 64 channels in REAPER by hand is painful, or wants to clean up empty / silent WAV files.
user_invocable: true
---

# REAPER routing

`scripts/route_reaper.py` reads a project REAPER saved and writes a new `.rpp` with the routing changed. It touches
only the track-level `NAME`, `REC`, `MAINSEND` and `HWOUT` lines; items, FX, envelopes and everything else stay
byte for byte, line endings included. The format and how sure each field is: [`reference/rpp-format.md`](reference/rpp-format.md).

## Safety

- Start from a project REAPER saved with the tracks already there (create 64 tracks in REAPER first; the script
  doesn't add tracks). Close the project in REAPER, or REAPER's next save overwrites the script's file.
- Write the new file **in the same folder** as the source: item paths like `Media\01-take.wav` are relative to the
  project. The script refuses to overwrite the source or an existing file.
- After the run, open the new file in REAPER and check the routing matrix (Alt+R / Option+R) before a show.

## Commands

```sh
python3 scripts/route_reaper.py SRC.rpp DEST.rpp [options]
```

| Option | Does |
|---|---|
| `--in 1-64` | record input N for track N (mono). `--in 41-64:17` = tracks 41-64 from input 17 on. Repeatable. |
| `--out 1-64` | one hardware out per track, track N → out N (mono, from track channel 1). `--out 1-8:33` = outs 33-40. Repeatable. Replaces the track's existing hardware outs. |
| `--stereo 7,41-42` | these tracks take an input pair and an output pair starting at the mapped channel (map them to odd channels). |
| `--master off` | master / parent send off, so playback reaches only the hardware outs. `on` turns it back on. |
| `--names FILE` | track names: `.emo` (LV1 inputs by index), `.scn` (X32 `/ch/NN/config`), `.snap` (WING `ch.N.name`), `.txt` (one per line), `.csv` (first column). Name N goes to track N. |
| `--device NAME` | with an LV1 `.emo`: name track N after what LV1 patched to channel N of this SoundGrid DAW device (the recording computer, as LV1's device list or its hostname shows it; case and `-` / `_` / spaces ignored). Stereo LV1 channels get ` L` / ` R`; unpatched channels keep their name. Use this whenever the recording went through an LV1 patch. |
| `--arm all` / `--arm 1-40` | record-arm tracks. `--disarm 33-40` disarms (applied after `--arm`). |
| `--monitor off` | record monitoring off (`on`, `tape` = not when playing), so armed tracks don't echo their input to the hardware outs. |
| `--only 1-40` | change only these tracks. |
| `--src-stereo` | mono hardware outs take track channels 1/2 mixed to mono (REAPER's default when routed by hand) instead of channel 1. |

## Workflow: one project for recording and virtual soundcheck

Build **one** file: every track armed, input monitoring off, hardware outs 1:1, master off, names. It records as is,
and the same file plays back to the console for virtual soundcheck (armed tracks with monitoring off play their
items and don't echo the live input).

```sh
python3 scripts/route_reaper.py show.rpp show_routed.rpp --in 1-64 --out 1-64 --master off \
  --names show.emo --device REC-PC --arm all --monitor off
```

Then show the user the track sheet and **ask which tracks to disarm**: a disarmed track records no file, which
saves disk (24-bit / 48 kHz mono is about 8.6 MB per minute per track). With `--device`, the script prints the
tracks LV1 doesn't feed; suggest those. Apply the answer with a second run on the routed file into a new name
(`--disarm 33-40,59-64`) and delete the intermediate file you wrote, so the user ends with one project.

## Cleanup after a recording

Takes that recorded only silence (a spare channel, a player that never started) still take disk space. The
ReaScript [`scripts/cleanup_silent_takes.lua`](scripts/cleanup_silent_takes.lua) cleans them from inside REAPER:
the user loads it once (Actions > Show action list > New action > Load ReaScript, then a toolbar button via right-click
on the toolbar > Customize toolbar > Add, or a shortcut) and runs it. It asks for the threshold (default -80 dBFS),
then opens a window with scan progress and the list of silent takes (track, level, size; digital silence = nothing
patched, around -80 dBFS = an input with nothing playing), plus takes whose file is missing (offline, e.g. after
undoing a removal whose WAVs were deleted), which the user would otherwise get a missing-file message for when
reopening the project. **Remove** takes the items out in one undo step; the
**Also delete the WAV files** checkbox (off by default) also deletes the files nothing else uses. After deleting,
tell the user to save right away. If Windows keeps a file open, the window says so; then save and use File > Clean
current project directory.

## Learn from the run: offer a pull request

This skill gets better from the people who use it. At the end of every run, check whether the run taught the skill something that would help the next user:

- the script failed, was refused where it shouldn't be, or gave a wrong result
- REAPER showed a value differently from what was written, dropped it, or refused the file
- a field or behaviour not in [`reference/rpp-format.md`](reference/rpp-format.md), or an item there proven or disproven by a REAPER load
- a routing feature the user needed that the script doesn't do

Show-specific content isn't a lesson: the user's track names and patch stay in their own files.

If there is a lesson:

1. **Make the change in this skill folder**, kept generic (no band, venue, channel or device names), following the repo's `AGENTS.md` and `CONTRIBUTING.md`: `SKILL.md` and `reference/rpp-format.md` updated with the scripts, tests added, Python standard library only. A fix to `scripts/contribute.sh` is the exception: the script is shared by every skill and publishes only this folder, so offer an issue for it instead of a pull request.
2. **Write the PR body** to a scratch file: what changed, what happened in the run that showed it, and evidence (REAPER version and OS, the script's output, what REAPER's routing matrix showed after loading the result). No project files or show names.
3. **Dry run and ask.** Run `bash <skill-dir>/scripts/contribute.sh --title "<title>" --body-file <file> --dry-run`, show the user the output (GitHub account, commit author, files) and ask whether to open the pull request from their account. Offer their GitHub noreply address with `--email` if they'd rather not publish their email.
4. **Only after a clear yes**, run it without `--dry-run` and give the user the PR link.

If the user found a bug but no fix, or has no GitHub CLI, offer an issue at https://github.com/DominikKriss/mixing-console-skills/issues/new/choose with the same body instead. The script is the same in every skill (see `lv1-session/SKILL.md` for its details).
