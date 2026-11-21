---
name: lv1-session
description: >-
  Build, edit or review a Waves eMotion LV1 session (.emo) by script. Build: input / FX / Mon / Matrix names,
  faders, monitor sends with pick-off points, FX returns, Mon / Matrix mono-stereo, Matrix sources, and eMo
  F2 / D5 / Q4, trim and polarity converted from a Behringer X32 scene (.scn). Edit a session the user already
  worked on: copy one Mon / Matrix bus (rack, Nx IEM type and positions, matrix levels) to others, add a plugin
  from one bus to others, Sends-on-Fader and talkback user keys, talkback presets. Review: readable diff of two
  sessions. Use when the user asks to prepare, change, fill or review an LV1 show / session / scene, move from
  an X32 to LV1, copy X32 channel processing into LV1, set up IEM / monitor mixes in LV1, or edit an .emo file.
user_invocable: true
---

# LV1 session builder

An `.emo` session is a plain SQLite database. Three scripts, all writing to a copy and never to the source:

- `scripts/build_lv1_session.py`: a new session from the user's saved one, a JSON layout and optionally an X32 scene (**Build**).
- `scripts/edit_lv1_session.py`: changes to a session the user has already edited in LV1, from a JSON edits file (**Edit**). Once the user works in LV1, use this, not a rebuild: a rebuild drops their hand-made changes.
- `scripts/diff_lv1_sessions.py`: a readable diff of two sessions (**Review**).

The file format is documented in [`reference/emo-format.md`](reference/emo-format.md); read it before changing the scripts.

## Safety (every mode)

- Inspect sessions read-only with `sqlite3 "file:<f>?immutable=1"` (plain `-readonly` fails). Work on copies in a scratch folder; keep the user's file as the backup.
- Before overwriting a file you wrote earlier (e.g. on the user's USB stick), `cmp` it with your last copy. If it differs, the user saved it in LV1: start again from their file.
- Use a new file name (`<name>_05.emo`) unless the user asked to overwrite. Never write `CurrentLV1.dat`.
- Every build and edit run ends with `integrity: ok` and `presets with wrong ref_count: 0`; anything else is a failed run. The review diff prints nothing when the two sessions are the same.
- Tell the user to load the new session from LV1's session menu before saving anything: LV1 keeps the open session in memory and Save overwrites a script edit.

## Inputs

- **Source session:** a session the user saved in LV1 or the LV1 Session Editor, in `/Users/Shared/Waves/eMotion/Sessions/<name>.emo` on macOS. On Windows Waves documents `C:\Users\Public\Waves Audio\eMotion\Sessions\` on a computer and `D:\Users\Public\Waves Audio\eMotion\Sessions\` on an LV1 Classic console; the folder can be changed in LV1, so ask the user if the file isn't there. Always start from a session the user saved, never from a blank file.
- **Layout config:** JSON, one per band / show, kept next to the user's project files (example: [`examples/layout.example.json`](examples/layout.example.json)):
  - `inputs`: LV1 channel names in order (index 0 = ch 1). An entry `{"name": "OH", "stereo": true}` makes a stereo input (eMo switched to the stereo variants at default). A plain name makes a mono input, also where the source session had a stereo one.
  - `rack` (optional): the same plugin rack on every input. `slots` maps the 1-based rack slot to a plugin name (`EMO-F2/D5/Q4` are moved, everything else is removed). Other plugins are copied from `donor`, a session the user saved with the plugin in use (path relative to the layout file). `plugins.<name>.channels` maps LV1 input → donor channel for that plugin's settings, `default.mono` / `default.stereo` name the donor channels used otherwise, `override` sets preset values by token position (e.g. Q1 gain = tokens 102/103). With `rack`, the X32 rack order is not applied; the report flags channels whose X32 comp ran pre-EQ.
  - `mons`: Mon aux in order. Each has `name`, `stereo`, an optional `matrix` (1-based matrix fed by this Mon, named `matrix_name` or the Mon name), `own` (inputs sent at `own_db` pre-fade in this mix) and `sends: false` for mixes left empty (spares).
  - `levels`: `other_db` (every other input, post-pan) and `own_db`. `always_pre_0db` lists inputs sent pre-fade at `own_db` into every mix (talkback); `no_mon_sends` lists inputs sent to no Mon mix (private talkback, measurement mic).
  - `fx`: FX aux in order. `feeds` maps input → `[dB, "INP"|"PRE"|"PST"|"PSP"]`; `dedicated_to` = the Mon name that gets this FX back at `fx_returns.own_db` (`other_db` everywhere else). FX without feeds are left as the source session has them, returns included; clear those returns in LV1 if that FX should stay out of the mixes.
  - `colors` (optional): `[{"value": 4, "inputs": [names], "mons": [1-based], "matrices": [...], "fx": [...], "groups": [...]}]` sets channel colours (`PARAM_COLOR_VALUE`); the palette index → colour table is in [`reference/emo-format.md`](reference/emo-format.md).
  - `x32_to_lv1`: X32 channel → LV1 channel (1-based). Needed only with an X32 scene.
- **X32 scene (optional):** a complete `.scn` exported from the X32 (check that `file` reports ASCII and that the file isn't truncated).

## Build a new session

1. **Ask for or find the layout and the X32 scene.** If the user keeps project notes, read them first.
2. **Copy the source session into the user's working folder** (`<name>.orig.emo`) as the backup. Inspect it read-only with `sqlite3 "file:<f>?immutable=1"`: plain `-readonly` fails.
3. **Write or update the layout config.** The script exits if any name in `own`, `feeds` or `always_pre_0db` is not in `inputs`.
4. **Run the build into the working folder:**
   ```
   python3 <skill-dir>/scripts/build_lv1_session.py <orig.emo> <work-dir>/<name>.emo <layout.json> [<scene.scn>]
   ```
   The output lists each X32 → LV1 channel with its rack order and any clamped value. The last line must say `integrity: ok` and show `preset refs N/N` (equal).
5. **Put the result where the user loads sessions from** (Sessions folder or their USB stick), following **Safety** above.
6. **Verify with the user on one channel with dynamics and EQ.** Check:
   - trim and polarity
   - rack order
   - F2 frequency
   - Q4 type, frequency, gain and Q per band
   - D5 gate (open, floor, key filters)
   - D5 comp (threshold, ratio, knee, Manual release, makeup)
   - Mon / Matrix stereo and matrix levels

## Edit an existing session

Edits file (JSON, example: [`examples/edits.example.json`](examples/edits.example.json)); bus numbers and rack slots are 1-based, applied in this order:

- `names`: `{"mon": {"16": "TB FOH"}}` (also `matrix`, `fx`, `input`).
- `copy_bus`: `[{"type": "mon"|"matrix", "from": 1, "to": [2, 3], "nx_positions": true}]`. Copies the rack (plugins with their settings and bypass), mono / stereo, the Nx IEM type (Mon) and matrix source levels and assignment type (Matrix). Target matrix source levels are replaced, not merged, snapshot by snapshot. `nx_positions` copies every input's Nx rotate / width from the source mix; positions at their default in the source are reset in the target. The usual pattern: the user sets up one mix by hand in LV1 and the script copies it to the rest.
- `add_plugin`: `[{"from": {"type": "cue", "index": 1, "slot": 4}, "to": {"type": "matrix", "index": [1, 2]}, "slot": 7}]`. The target slot must be free and the plugin's mono / stereo variant must match the target bus. Types: `input`, `group`, `fx`, `mon`, `matrix`, `cue`, `talkback`.
- `matrix_gain`: `{"matrices": [1, 2], "db": 0.0}`: level of each matrix's first source (default −∞, so a new matrix is silent).
- `talkback`: `{"presets": [{"name": "TB BAND", "mons": [1, 2], "fx": []}], "master_db": 0.0, "send_db": 0.0}`. Up to 8 presets; they replace the session's presets. Talkback reaches buses only, so talk to another console goes through a Mon bus patched to an output.
- `user_keys`: `[{"key": 1, "sof_mon": 1}, {"key": 13, "talkback": "TB BAND"}, {"key": 5, "clear": true}]`. Talkback keys need the `talkback` edit in the same file.

```
python3 <skill-dir>/scripts/edit_lv1_session.py <user.emo> <work-dir>/<name>_NN.emo <edits.json>
python3 <skill-dir>/scripts/diff_lv1_sessions.py <user.emo> <work-dir>/<name>_NN.emo
```

Check the diff shows only the intended changes, then copy the result to where the user loads sessions from.

## Review a session

`diff_lv1_sessions.py <before.emo> <after.emo>` lists, by bus type and number: names, bus width / Nx type, parameters, Matrix sources, plugin racks (name, mono/stereo variant, preset hash, bypass), user keys, talkback presets and patching. Use it to review what the user changed in LV1 since the last known version, and to check every script run. Things worth flagging in a review:

- Matrix with source level −∞ (`PARAM_INPUT_MATRIX_GAIN_0` absent or −144): silent.
- Stereo Mon / Matrix with mono eMo variants (CFLM / CDYM / MQ4M).
- EMO-IEM on a Mon that isn't Nx type (`is_input_nx` 0).
- Patching shifted around stereo inputs (one stereo channel takes two device channels).
- Big trim jumps, processing bypassed on key channels, unusual plugin choices: ask, don't change; input processing is the engineer's work.

Plugin settings other than eMo can't be decoded without the plugin's ParamXML installed; say so instead of guessing.

## Conversion rules (X32 → eMo)

- **Trim:** X32 trim goes to LV1 digital trim, max +10 dB. The rest goes to the Q4 output gain. Where D5 runs before Q4, its gate and comp thresholds are lowered by that rest, so D5 acts on the level the X32 dynamics saw (reported).
- **High-pass:** X32 low cut → F2 HPF.
- **EQ:** the four X32 bands are placed into Q4 slots in frequency order, within each slot's limits:
  - band 1: Bell / Low-Shelf / Hi-Pass
  - band 2: Bell / Low-Shelf
  - band 3: Bell / Hi-Shelf
  - band 4: Bell / Hi-Shelf / Low-Pass

  Flat bands are switched off, like every Q4 band the X32 doesn't use (the stock Q4 default has all four on at 0 dB). A band that doesn't fit is dropped and reported.
- **Rack order:** an X32 compressor set to POST EQ → F2 → Q4 → D5; otherwise F2 → D5 → Q4. The order is set, not swapped, so a rebuild from an earlier output gets the same order. With `rack`, each eMo plugin may appear in one slot only; a missing eMo plugin is reported and its settings skipped. A bypassed F2 / D5 / Q4 that gets settings stays bypassed and is reported. Plugins still used by a hot-plug key or MIDI learn are never removed: the build stops.
- **Gate:** GATE mode only; EXP2-4 and DUCK are reported and the D5 gate left off (the D5 expander code isn't known yet). Floor = −range; release capped at 1000 ms. X32 bandpass key filters become HPF/LPF at the −3 dB edges.
- **Compressor:** COMP mode only; EXP is reported and the D5 comp left off.
  - ratio capped at 20
  - knee: X32 0 → Hard, 1–2 → Normal, 3–5 → Soft
  - release Manual, written to `PARAM_COMP_MAX_REL`
- **Not converted:** X32 preamp gain and phantom (set on the stagebox), and PEAK/RMS and LIN/LOG detection (no D5 equivalent).

## Not done by the scripts

Patching and I/O devices, and plugins that exist nowhere in the session or a donor. Stored snapshots are written like the Active state, but only sessions without stored snapshots have been checked in LV1. For anything unknown, never guess a code: have the user make the change once by hand in LV1 and save under a new name (e.g. one user key, one bus), diff it against the previous file with `diff_lv1_sessions.py`, record the finding in `reference/emo-format.md`, then script it. A save of the stock defaults won't show the field, because parameters at their default value aren't stored.

## Learn from the run: offer a pull request

This skill gets better from the people who use it. At the end of every run (any mode), check whether the run taught the skill something that would help the next user:

- a script failed, gave a wrong result or needed a fix or workaround
- a field, code or behaviour not in [`reference/emo-format.md`](reference/emo-format.md), e.g. found by diffing a by-hand change
- a rule here that was wrong, missing or unclear, or an X32 → eMo conversion that LV1 showed differently
- a new kind of edit or check the user needed that the scripts don't do

Show-specific content isn't a lesson: the user's layout, channel names, levels and taste stay in their own files.

If there is a lesson:

1. **Make the change in this skill folder**, kept generic (no band, venue, channel or device names), following the repo's `CONTRIBUTING.md`: `SKILL.md` and `reference/emo-format.md` updated with the scripts, Python standard library only. A fix to `scripts/contribute.sh` is the exception: the script is shared by every skill (CI checks the copies match) and publishes only this folder, so offer an issue for it instead of a pull request.
2. **Write the PR body** to a scratch file: what changed, what happened in the run that showed it, and evidence (LV1 version, the `integrity: ok` lines, the relevant `diff_lv1_sessions.py` lines, whether LV1 loaded the result and showed the change). No session files or show names.
3. **Dry run and ask.** Run `bash <skill-dir>/scripts/contribute.sh --title "<title>" --body-file <file> --dry-run`. Tell the user in two or three lines what the skill learned, show the dry-run output (GitHub account, commit author, files) and ask whether to open the pull request from their account. If the commit author email is one they'd rather not publish, offer their GitHub noreply address (`<id>+<login>@users.noreply.github.com`) with `--email`.
4. **Only after a clear yes**, run it again without `--dry-run` and give the user the PR link. The maintainer reviews it; the user's local copy keeps the change meanwhile. On a no, leave the change local or revert it, as the user prefers.

The script needs the GitHub CLI logged in (`gh auth login`). It forks the repo to the user's account, commits only this skill folder on a `learn/…` branch and refuses session / scene files, files staged outside the skill folder, and local commits that aren't on upstream `main`. If pushing or opening the PR fails after the commit, run it again on the same `learn/…` branch: it publishes the existing commit instead of making a new one. `--email` also overrides `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL`. After opening the PR it asks CodeRabbit for a review; mention its comments to the user, the maintainer decides. If the skill was copied rather than cloned, it compares the folder with a fresh clone of `main`; check the file list for upstream changes showing as removed. Without `gh`, offer an issue at https://github.com/DominikKriss/mixing-console-skills/issues with the same body instead.

## Tests

Every script has a test file in `tests/` (Python `unittest`, standard library only). The tests build small synthetic sessions, eMo ParamXML and X32 scenes in `tests/fixtures.py`; never add a real `.emo` or `.scn`. Run them from the skill folder before every change and add a test with each fix or new edit type:

```
python3 -m unittest discover -s tests -t tests
```

CI runs them on every pull request (macOS and Linux).

## Prerequisites

- Python 3 and `sqlite3` (macOS has both).
- The eMo F2, D5 and Q4 plugins installed through Waves Central (the LV1 Session Editor also needs them to show plugins). The script reads each plugin's parameter order from `/Applications/Waves/Plug-Ins V*/EMO-*.bundle/Contents/Resources/ParamXML/1000.xml`; set `LV1_EMO_PARAMXML_DIR` to a folder with `EMO-F2-ParamXML.xml` etc. to override. It refuses a preset whose value count differs from the ParamXML.
- Tested with LV1 17.3 on macOS; other versions may store things differently.
