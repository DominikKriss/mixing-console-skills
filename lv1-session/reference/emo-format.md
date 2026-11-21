# LV1 session (.emo) format

Found by reverse-engineering LV1 17.3 sessions (not documented by Waves).

## Summary

An LV1 `.emo` session (v17.3) is a plain SQLite database and can be edited with a script. Channel settings are named parameters stored only when they differ from the default. Plugin settings are XML preset chunks that list values by position.

## Details

- **Open read-only with** `sqlite3 "file:x.emo?immutable=1"`: plain `-readonly` fails with "unable to open database file". Sessions live in `/Users/Shared/Waves/eMotion/Sessions/` (macOS); Waves documents `C:\Users\Public\Waves Audio\eMotion\Sessions\` on Windows (unconfirmed by a save here). `CurrentLV1.dat` (+ `-wal`) is LV1's live state; don't write to it.
- **LV1 keeps the open session in memory.** Save writes that state over the file, so a script edit is lost unless the session is loaded again first. Edit a copy, then load it from the session menu.
- **Objects:** `object` (`obj_type` → `cluster_type`: 0 Input, 1 Group, 2 Aux (FX), 6 Matrix, 25 Mon). The name is in `snapshot_chainer.name` per snapshot (-1 = Active, 0.. = stored).
- **Nx (immersive IEM) Mon type:** `chainer.is_input_nx` 1 on the Mon aux. Without it the EMO-IEM plugin and the send rotate / width (`PARAM_AUX_SEND_ROTATE_NX_<slot>`, `..._WIDTH_NX_<slot>`) do nothing; copying the rack alone isn't enough. Positions are per input per Mon (slot numbering as the sends: Mon 1 = `_8`); the EMO-IEM plugin holds no positions.
- **Mono/stereo:** `chainer.num_inputs` 1 / 2 on Mon aux and Matrix. Switching to stereo by script does not swap the plugins: the mono variants (CFLM/CDYM/MQ4M) stay until the plugs are replaced with the stereo variants (CFLS/CDYS/MQ4S); LV1 did this on Mon 1 / Matrix 1 only after the owner worked on them.
- **Parameters:** `snapshot_chainer_params(chainer_id, snapshot_id, param_id, value)`. Names are in `chainer_params` and defaults in `chainer_params_default_values`.
  - Sends `PARAM_AUX_SEND_{GAIN,ONOFF,SOURCE}_<slot>`: FX 1-8 = slots 0-7, Mon 1-8 = 8-15, Mon 9-16 = `2_0`-`2_7`, Mon 17-24 = `3_0`-`3_7`.
  - Gain is stored in dB (-144 = off) and On = 1.
  - SOURCE: 0 INP, 1 PRE, 2 PST, 3 PSP. FX sends default to 3, Mon sends to 1.
  - `PARAM_OUTPUT_GAIN` is the fader (default -144).
- **Channel colour:** `PARAM_COLOR_VALUE` = palette index 0-31, same param on inputs, groups, FX aux, Mon and Matrix. Defaults: input 13, group 11, FX aux 2, Mon 3, Matrix 8. Palette as LV1 17.3 shows it (read from a screenshot of a session coloured 0-31, names approximate):

  | # | colour | # | colour | # | colour | # | colour |
  |---|---|---|---|---|---|---|---|
  | 0 | slate teal | 8 | strong blue | 16 | purple | 24 | orange |
  | 1 | blue | 9 | cyan | 17 | salmon | 25 | magenta |
  | 2 | olive green | 10 | light cyan | 18 | yellow | 26 | lavender |
  | 3 | green | 11 | dark teal | 19 | red | 27 | pink |
  | 4 | light grey-blue | 12 | grey-blue | 20 | white | 28 | dark olive |
  | 5 | slate grey | 13 | teal | 21 | dark red | 29 | mauve |
  | 6 | amber | 14 | bright green | 22 | lime | 30 | rose |
  | 7 | crimson pink | 15 | mint | 23 | grey | 31 | violet |

  Strong / light pairs of one hue: 9/10 cyan, 14/15 green, 16/26 purple, 19/17 red, 24/6 orange, 1/12 blue.
- **Trim and polarity:** the UI reads `PARAM_INPUT_DIGITAL_TRIM_L/_R` and `PARAM_INPUT_PHASE_ONOFF_L/_R`; writing only the base param doesn't show. Trim max is +10 dB.
- **Matrix source:** a row in `snapshot_assignment` (src = Mon object, `src_section_type` 7, control 0; dst = Matrix object, `dst_section_type` 0, `dst_section_index` = source slot). LV1 writes `src_asgn_type` 1 for a stereo Mon → stereo Matrix (the script wrote 0). The source level is `PARAM_INPUT_MATRIX_GAIN_<slot>` on the Matrix, default -144 (silent): set it, or the matrix outputs nothing.
- **User keys:** `user_keys(key_index 0-15, key_action, selection_index, obj_type, obj_index, uk_friendly_name)`. Seen: action 0 = unassigned, 25 = talkback (selection_index 1/2), 51 = mute group (obj_type 13), 27 = Sends on Fader (selection_index 0, obj_type 25 Mon, obj_index = Mon 0-based; from an owner-saved key on Mon 1). Talkback key: action 25, selection_index = talkback preset ID + 1.
- **Talkback presets:** `talk_back_specific_data.preset` on the TalkBack object (obj_type 8): `<TB_Presets>` with `<TB_Preset ID="0-7">` listing `<Param ID="<chainer_params id>" State="0|1"/>` for the destination ON/OFF params (`PARAM_AUX_SEND_ONOFF_*` for FX / Mon, `PARAM_OUTPUT_ASSIGNMENT_*`, CR 1-4; IDs 727-734 have no name but LV1 writes them). The talkback master (`PARAM_OUTPUT_GAIN`) and send gains default to -144: set them. There are no direct-output destinations: talk to another console goes through a Mon bus patched to an output (the FOH session uses Mon 16 `TB FOH`).
- **Plugins:**
  - `plug(chainer_id, slot, plugin_name)` sets the rack order.
  - `snapshot_plugin.preset_id` points to `plugin_preset(hash, ref_count, preset)`.
  - The hash is SHA3-256 of the chunk text. `ref_count` = number of `snapshot_plugin` rows using the preset; triggers on `snapshot_plugin` insert / update / delete keep it (and delete presets at 0), so never adjust it by hand.
  - `plug` slot is 0-based (rack slot 1 = 0), any order; eMo have `plug_role` 4 F2, 1 D5, 2 Q4, other plugins 0. `plugin_4cc` ends in M / S for mono / stereo (CFLM/CFLS, VXPM/VXPS PSE, EQ1M/EQ1S Q1).
  - A plugin is added with a `plug` row plus one `snapshot_plugin` row per snapshot (setup_type -1, docked 1); a preset chunk copies between sessions unchanged. Deleting a plug: delete its `snapshot_plugin` and `plug_sidechain` rows first (foreign keys are off, the cascade doesn't run).
  - Q1 (`Q10` / EQ1M): output gain L/R = tokens 102 / 103 of each `<Parameters>` block.
- **Stereo input:** `chainer.num_inputs` 2 and the stereo plugin variants (`plugin_4cc` …S with a stereo preset chunk; the stock defaults are in every session, used by Groups / FX).
- **Preset chunks:** `<Parameters Type="RealWorld">` holds the values in the order of the plugin's `Contents/Resources/ParamXML/1000.xml` (in `/Applications/Waves/Plug-Ins V*/EMO-*.bundle`); `*` = display-only.
  - The Session Editor shows no plugins until they're installed through Waves Central.
  - eMo codes:
    - Q4 stock default: all four bands ON at 0 dB (`PARAM_BAND_STATE`, `PARAM_BAND<n>_STATE_L/_R` = 1).
    - Q4 band 1 type: 0 Bell, 1 Low-Shelf, 2 Hi-Pass. Band 2: Bell / Low-Shelf. Band 3: Bell / Hi-Shelf. Band 4: Bell, Hi-Shelf, Low-Pass.
    - D5 knee: 0 Soft, 1 Normal, 2 Hard.
    - D5 release mode: 0 Manual. The release knob is `PARAM_COMP_MAX_REL`.
    - Gate/Exp: 0 Gate.
    - All of these were confirmed in LV1 on KICK.
    - D5 is gate + compressor in one plugin: an EQ between gate and comp needs a second D5 (gate-only, comp-only).
