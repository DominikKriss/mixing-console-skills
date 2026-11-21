"""Synthetic LV1 sessions, eMo ParamXML and X32 scenes for the tests. Nothing here comes from a real show."""
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lv1db import send_suffix  # noqa: E402

T_INPUT, T_GROUP, T_FX, T_MATRIX, T_CUE, T_TB, T_MON = 0, 1, 2, 6, 7, 8, 25

# Same tables, columns and ref_count triggers as an LV1 17.3 session, without the tables the scripts don't touch.
SCHEMA = """
CREATE TABLE cluster_type (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE object (id INTEGER NOT NULL PRIMARY KEY, obj_type INTEGER NOT NULL, obj_index INTEGER NOT NULL,
  name TEXT, ch_scope_type_id INTEGER NOT NULL DEFAULT 0, recall_safe NUMERIC DEFAULT 0, UNIQUE (obj_type, obj_index));
CREATE TABLE chainer (obj_id INTEGER NOT NULL UNIQUE, num_inputs INTEGER NOT NULL DEFAULT -1,
  num_outputs INTEGER NOT NULL DEFAULT -1, input_stem_format INTEGER NOT NULL DEFAULT 0,
  output_stem_format INTEGER NOT NULL DEFAULT 0, sgs_processing_group INTEGER NOT NULL DEFAULT 0,
  is_input_nx INTEGER NOT NULL DEFAULT 0);
CREATE TABLE snapshot (id INTEGER NOT NULL PRIMARY KEY, ext_id INTEGER DEFAULT null, number INTEGER NOT NULL UNIQUE,
  name TEXT, note TEXT, info TEXT, tempo REAL NOT NULL DEFAULT 120, sync_tempo NUMERIC DEFAULT 0);
CREATE TABLE snapshot_chainer (id INTEGER NOT NULL PRIMARY KEY, chainer_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL, name TEXT NOT NULL, preset_name TEXT NOT NULL DEFAULT '',
  selected_slot INTEGER DEFAULT -1, ch_scope_type_id INTEGER NOT NULL DEFAULT 0, in_scope INTEGER NOT NULL DEFAULT 1,
  UNIQUE (chainer_id, snapshot_id));
CREATE TABLE chainer_params (id INTEGER NOT NULL PRIMARY KEY, name TEXT);
CREATE TABLE snapshot_chainer_params (chainer_id INTEGER NOT NULL, snapshot_id INTEGER NOT NULL,
  param_id INTEGER NOT NULL, param_value REAL NOT NULL, PRIMARY KEY (chainer_id, snapshot_id, param_id)) WITHOUT ROWID;
CREATE TABLE plug (id INTEGER NOT NULL PRIMARY KEY, chainer_id INTEGER NOT NULL, slot INTEGER NOT NULL,
  plugin_name TEXT NOT NULL, plugin_4cc TEXT NOT NULL, additional_info TEXT NOT NULL DEFAULT '',
  disabled NUMERIC NOT NULL, recall_safe NUMERIC DEFAULT 0, side_chain NUMERIC NOT NULL,
  hot_plugin INTEGER NOT NULL DEFAULT -1, vendor_name TEXT DEFAULT '', plug_role INTEGER NOT NULL DEFAULT 0,
  ignore_latency NUMERIC NOT NULL DEFAULT 'FALSE', UNIQUE (slot, chainer_id));
CREATE TABLE plug_sidechain (id INTEGER NOT NULL PRIMARY KEY, plug_id INTEGER NOT NULL UNIQUE,
  AsgnType INTEGER NOT NULL, ControlType INTEGER NOT NULL, sidechain_src_chainer_id INTEGER NOT NULL,
  SectionType INTEGER NOT NULL, SectionIndex INTEGER NOT NULL, ChannelIndex INTEGER NOT NULL,
  controlID INTEGER NOT NULL);
CREATE TABLE plugin_preset (id INTEGER NOT NULL PRIMARY KEY, hash TEXT NOT NULL UNIQUE,
  ref_count INTEGER NOT NULL DEFAULT 0, preset TEXT NOT NULL);
CREATE TABLE snapshot_plugin (id INTEGER NOT NULL PRIMARY KEY, plug_id INTEGER NOT NULL, preset_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL, setup_type_id INTEGER NOT NULL, bypass NUMERIC NOT NULL, mute NUMERIC NOT NULL,
  docked NUMERIC NOT NULL DEFAULT true, fw_posx INTEGER DEFAULT -9999, fw_posy INTEGER DEFAULT -9999,
  fw_scale_precentage INTEGER DEFAULT -1, fw_always_on_top NUMERIC DEFAULT false, dw_posx INTEGER DEFAULT -9999,
  dw_posy INTEGER DEFAULT -9999, dw_scale_precentage INTEGER DEFAULT -1, UNIQUE (plug_id, snapshot_id, setup_type_id));
CREATE TRIGGER delete_snapshot_plugin_trigger AFTER DELETE ON snapshot_plugin BEGIN
  UPDATE plugin_preset SET ref_count = ref_count - 1 WHERE id = old.preset_id;
  DELETE FROM plugin_preset WHERE ref_count = 0 AND id = old.preset_id; END;
CREATE TRIGGER insert_snapshot_plugin_trigger AFTER INSERT ON snapshot_plugin BEGIN
  UPDATE plugin_preset SET ref_count = ref_count + 1 WHERE id = new.preset_id; END;
CREATE TRIGGER update_snapshot_plugin_trigger AFTER UPDATE OF preset_id ON snapshot_plugin BEGIN
  UPDATE plugin_preset SET ref_count = ref_count + 1 WHERE id = new.preset_id;
  UPDATE plugin_preset SET ref_count = ref_count - 1 WHERE id = old.preset_id;
  DELETE FROM plugin_preset WHERE ref_count = 0 AND id = old.preset_id; END;
CREATE TABLE snapshot_assignment (id INTEGER NOT NULL PRIMARY KEY, snapshot_id INTEGER NOT NULL,
  src_id INTEGER NOT NULL, src_section_type INTEGER NOT NULL, src_section_index INTEGER NOT NULL,
  src_channel_index INTEGER NOT NULL, src_control_id INTEGER NOT NULL, src_asgn_type INTEGER NOT NULL,
  dst_id INTEGER NOT NULL, dst_section_type INTEGER NOT NULL, dst_section_index INTEGER NOT NULL,
  dst_channel_index INTEGER NOT NULL, dst_control_id INTEGER NOT NULL, dst_asgn_type INTEGER NOT NULL,
  status INTEGER NOT NULL);
CREATE TABLE user_keys (id INTEGER NOT NULL PRIMARY KEY, key_index INTEGER NOT NULL UNIQUE,
  key_action INTEGER NOT NULL, selection_index INTEGER DEFAULT -1, obj_type INTEGER DEFAULT -1,
  obj_index INTEGER DEFAULT -1, uk_friendly_name TEXT NOT NULL);
CREATE TABLE talk_back_specific_data (chainer_id INTEGER NOT NULL UNIQUE, preset TEXT NOT NULL);
CREATE TABLE routes (id INTEGER NOT NULL PRIMARY KEY, src_cluster_type INTEGER NOT NULL,
  src_cluster_type_index INTEGER NOT NULL, src_section_type INTEGER NOT NULL, src_section_index INTEGER NOT NULL,
  src_channel_index INTEGER NOT NULL, src_control_id INTEGER NOT NULL, src_asgn_type INTEGER NOT NULL,
  dst_cluster_type INTEGER NOT NULL, dst_cluster_type_index INTEGER NOT NULL, dst_section_type INTEGER NOT NULL,
  dst_section_index INTEGER NOT NULL, dst_channel_index INTEGER NOT NULL, dst_control_id INTEGER NOT NULL,
  dst_asgn_type INTEGER NOT NULL, status INTEGER NOT NULL);
CREATE TABLE hot_plug (number INTEGER NOT NULL PRIMARY KEY, plug_id INTEGER DEFAULT -1);
CREATE TABLE midi_learn (id INTEGER NOT NULL PRIMARY KEY, plug_id INTEGER DEFAULT -1);
"""

CLUSTER = {0: "Input", 1: "Group", 2: "Aux", 6: "Matrix", 7: "Cue", 8: "TalkBack", 25: "Mon"}

DISPLAY = ["PARAM_IN_VU_L", "PARAM_IN_VU_R"]
F2 = DISPLAY + [f"PARAM_{s}_{p}" for s in "LR" for p in ("HPF_ON", "HPF_FREQ", "LPF_ON", "LPF_FREQ")]
Q4 = DISPLAY + ["PARAM_BAND_STATE", "PARAM_BAND_TYPE", "PARAM_BAND_GAIN", "PARAM_BAND_FRQ", "PARAM_BAND_QF"] + [
    f"PARAM_BAND{b}_{x}_L" for b in range(2, 5) for x in ("STATE", "TYPE", "GAIN", "FREQ", "Q")] + [
    f"PARAM_BAND{b}_{x}_R" for b in range(1, 5) for x in ("STATE", "TYPE", "GAIN", "FREQ", "Q")] + [
    "PARAM_OUT_GAIN_L", "PARAM_OUT_GAIN_R"]
D5 = DISPLAY + [f"PARAM_GATE_{x}" for x in ("ON", "EXP", "THRESH", "FLOOR", "ATT", "HOLD", "REL", "HPF_ON", "LPF_ON",
                                            "HPF_FREQ", "LPF_FREQ")] + [
    f"PARAM_COMP_{x}" for x in ("ON", "THRESH", "RATIO", "KNEE", "ATT", "REL_MODE", "MAX_REL", "MAKEUP", "MIX",
                                "HPF_ON", "LPF_ON", "HPF_FREQ", "LPF_FREQ")]
EMO_PARAMS = {"EMO-F2": F2, "EMO-Q4": Q4, "EMO-D5": D5}
EMO_PLUGS = [("EMO-F2", "CFLM", "CFLS", 4), ("EMO-D5", "CDYM", "CDYS", 1), ("EMO-Q4", "MQ4M", "MQ4S", 2)]


def write_paramxml(directory):
    """ParamXML files in the LV1_EMO_PARAMXML_DIR layout. Returns the directory."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for plugin, names in EMO_PARAMS.items():
        body = "".join(f'  <Parameter Name="{n}"></Parameter>\n' for n in names)
        (d / f"{plugin}-ParamXML.xml").write_text(f'<Parameter_List version="1">\n{body}</Parameter_List>\n', encoding="utf-8")
    return d


def chunk(plugin, subcomp, values=None):
    """Preset chunk with RealWorld values; display-only params are '*'."""
    if plugin in EMO_PARAMS:
        names = EMO_PARAMS[plugin]
        toks = ["*" if n in DISPLAY else str((values or {}).get(n, 0)) for n in names]
    else:
        toks = [str(v) for v in (values or [0] * 110)]
    lines = "\n".join(" ".join(toks[i:i + 10]) for i in range(0, len(toks), 10))
    block = f'   <Parameters Type="RealWorld">\n{lines}\n</Parameters>\n'
    return (f'<PresetChunkXMLTree version="3">\n <Preset Name="">\n  <PresetHeader>\n'
            f"   <PluginName>{plugin}</PluginName>\n   <PluginSubComp>{subcomp}</PluginSubComp>\n  </PresetHeader>\n"
            f'  <PresetData Setup="SETUP_A">\n{block}  </PresetData>\n'
            f'  <PresetData Setup="SETUP_B">\n{block}  </PresetData>\n </Preset>\n</PresetChunkXMLTree>\n')


def param_names():
    names = ["PARAM_OUTPUT_GAIN", "PARAM_COLOR_VALUE", "PARAM_OUTPUT_ASSIGNMENT_LR"]
    names += [f"PARAM_INPUT_DIGITAL_TRIM{s}" for s in ("", "_L", "_R")]
    names += [f"PARAM_INPUT_PHASE_ONOFF{s}" for s in ("", "_L", "_R")]
    names += [f"PARAM_INPUT_MATRIX_GAIN_{i}" for i in range(8)]
    sfx = [send_suffix("fx", i) for i in range(8)] + [send_suffix("mon", i) for i in range(16)]
    for s in sfx:
        names += [f"PARAM_AUX_SEND_{x}_{s}" for x in ("GAIN", "ONOFF", "SOURCE", "ROTATE_NX", "WIDTH_NX")]
    return names


def store_preset(cur, text):
    h = hashlib.sha3_256(text.encode()).hexdigest()
    row = cur.execute("select id from plugin_preset where hash=?", (h,)).fetchone()
    if row:
        return row[0]
    cur.execute("insert into plugin_preset (hash, ref_count, preset) values (?,0,?)", (h, text))
    return cur.lastrowid


def add_plug(cur, chainer, slot, name, cc, preset_text, snaps, role=0, bypass=0):
    cur.execute("insert into plug (chainer_id, slot, plugin_name, plugin_4cc, disabled, side_chain, plug_role,"
                " vendor_name) values (?,?,?,?,0,0,?, 'Waves')", (chainer, slot, name, cc, role))
    plug = cur.lastrowid
    pid = store_preset(cur, preset_text)
    for s in snaps:
        cur.execute("insert into snapshot_plugin (plug_id, preset_id, snapshot_id, setup_type_id, bypass, mute)"
                    " values (?,?,?,-1,?,0)", (plug, pid, s, bypass))
    return plug


def make_session(path, inputs=4, fx=2, mons=4, matrices=4, snaps=(-1,)):
    """An LV1-like session: mono eMo F2 / D5 / Q4 at default on every input / Mon / Matrix, stereo on the FX buses."""
    path = str(path)
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    cur = db.cursor()
    cur.executescript(SCHEMA)
    cur.executemany("insert into cluster_type values (?,?)", CLUSTER.items())
    for s in snaps:
        cur.execute("insert into snapshot (id, number, name) values (?,?,?)", (s, s, "Active" if s == -1 else f"S{s}"))
    cur.executemany("insert into chainer_params (name) values (?)", [(n,) for n in param_names()])
    for plugin, mono, st, _role in EMO_PLUGS:
        store_preset(cur, chunk(plugin, mono))
        store_preset(cur, chunk(plugin, st))
    counts = {T_INPUT: inputs, T_FX: fx, T_MON: mons, T_MATRIX: matrices, T_CUE: 1, T_TB: 1}
    prefix = {T_INPUT: "IN", T_FX: "FX", T_MON: "MON", T_MATRIX: "MTX", T_CUE: "CUE", T_TB: "TB"}
    for t, n in counts.items():
        for i in range(n):
            cur.execute("insert into object (obj_type, obj_index) values (?,?)", (t, i))
            oid = cur.lastrowid
            cur.execute("insert into chainer (obj_id, num_inputs) values (?,1)", (oid,))
            for s in snaps:
                cur.execute("insert into snapshot_chainer (chainer_id, snapshot_id, name) values (?,?,?)",
                            (oid, s, f"{prefix[t]} {i + 1}"))
            if t in (T_INPUT, T_MON, T_MATRIX):
                for slot, (plugin, mono, _st, role) in enumerate(EMO_PLUGS):
                    add_plug(cur, oid, slot, plugin, mono, chunk(plugin, mono), snaps, role=role)
            if t == T_FX:
                cur.execute("update chainer set num_inputs=2 where obj_id=?", (oid,))
                for slot, (plugin, _mono, st, role) in enumerate(EMO_PLUGS):
                    add_plug(cur, oid, slot, plugin, st, chunk(plugin, st), snaps, role=role)
            if t == T_TB:
                cur.execute("insert into talk_back_specific_data values (?, '<TB_Presets />')", (oid,))
    for k in range(16):
        cur.execute("insert into user_keys (key_index, key_action, uk_friendly_name) values (?,0,'')", (k,))
    db.commit()
    db.close()
    return path


class Session:
    """Read helpers for assertions."""

    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.pid = dict(self.db.execute("select name, id from chainer_params"))

    def close(self):
        self.db.close()

    def oid(self, t, i):
        return self.db.execute("select id from object where obj_type=? and obj_index=?", (t, i)).fetchone()[0]

    def param(self, t, i, name, snap=-1, chainer=None):
        row = self.db.execute("select param_value from snapshot_chainer_params where chainer_id=? and snapshot_id=?"
                              " and param_id=?", (chainer or self.oid(t, i), snap, self.pid[name])).fetchone()
        return row[0] if row else None

    def set_param(self, t, i, name, value, snaps=(-1,)):
        for s in snaps:
            self.db.execute("insert or replace into snapshot_chainer_params values (?,?,?,?)",
                            (self.oid(t, i), s, self.pid[name], float(value)))
        self.db.commit()

    def width(self, t, i):
        return self.db.execute("select num_inputs, is_input_nx from chainer where obj_id=?",
                               (self.oid(t, i),)).fetchone()

    def rack(self, t, i):
        """[(slot 0-based, plugin_name, plugin_4cc)] in slot order."""
        return self.db.execute("select slot, plugin_name, plugin_4cc from plug where chainer_id=? order by slot",
                               (self.oid(t, i),)).fetchall()

    def preset(self, t, i, plugin, snap=-1):
        return self.db.execute(
            "select pp.preset from plug p join snapshot_plugin sp on sp.plug_id=p.id join plugin_preset pp"
            " on pp.id=sp.preset_id where p.chainer_id=? and p.plugin_name=? and sp.snapshot_id=?",
            (self.oid(t, i), plugin, snap)).fetchone()[0]

    def preset_values(self, t, i, plugin, snap=-1):
        """{param name: token} of the first <Parameters> block of an eMo plugin."""
        text = self.preset(t, i, plugin, snap)
        toks = text.split('<Parameters Type="RealWorld">')[1].split("</Parameters>")[0].split()
        return dict(zip(EMO_PARAMS[plugin], toks))

    def name(self, t, i):
        return self.db.execute("select name from snapshot_chainer where chainer_id=? and snapshot_id=-1",
                               (self.oid(t, i),)).fetchone()[0]


X32_ROUTING = "/config/routing/IN AN1-8 AN9-16 AN17-24 AN25-32 AUX/CR"


def x32_channel(n, name="CH", source=None, trim="+0.0", inv="OFF", hp=("OFF", "80"), eq_on="OFF", eq=None,
                gate=None, dyn=None, gate_mode="GATE", dyn_mode="COMP", dyn_pos="PRE", gate_filter=("OFF", "3.0", "1k00"), dyn_filter=("OFF", "3.0", "1k00")):
    """Lines of one /ch/NN block. eq: up to 4 (type, freq, gain, q); gate / dyn: dicts of overrides."""
    c = f"/ch/{n:02d}"
    bands = list(eq or []) + [("PEQ", "1k00", "+0.00", "2.0")] * (4 - len(eq or []))
    g = {"on": "OFF", "thr": "-40.0", "range": "60.0", "att": "0", "hold": "50", "rel": "200"} | (gate or {})
    d = {"on": "OFF", "thr": "-20.0", "ratio": "4.0", "knee": "1", "makeup": "0.0", "att": "10", "rel": "100",
         "mix": "100"} | (dyn or {})
    lines = [f'{c}/config "{name}" 1 RD {n if source is None else source}',
             f"{c}/preamp {trim} {inv} {hp[0]} 24 {hp[1]}",
             f"{c}/gate {g['on']} {gate_mode} {g['thr']} {g['range']} {g['att']} {g['hold']} {g['rel']} 0",
             f"{c}/gate/filter {' '.join(gate_filter)}",
             f"{c}/dyn {d['on']} {dyn_mode} PEAK LIN {d['thr']} {d['ratio']} {d['knee']} {d['makeup']} {d['att']} 0.02"
             f" {d['rel']} {dyn_pos} 0 {d['mix']} OFF",
             f"{c}/dyn/filter {' '.join(dyn_filter)}", f"{c}/eq {eq_on}"]
    lines += [f"{c}/eq/{i} {' '.join(b)}" for i, b in enumerate(bands, 1)]
    return lines


def write_scene(path, channels, headamps=None):
    """channels: {n: kwargs for x32_channel}. headamps: {index: (gain, phantom)}."""
    lines = ["#4.0# \"test\"", X32_ROUTING]
    for n, kw in sorted(channels.items()):
        lines += x32_channel(n, **kw)
    for i, (gain, ph) in sorted((headamps or {}).items()):
        lines.append(f"/headamp/{i:03d} {gain} {ph}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="latin-1")
    return str(path)


def ref_counts_ok(path):
    db = sqlite3.connect(str(path))
    bad = db.execute("select count(*) from plugin_preset pp where ref_count !="
                     " (select count(*) from snapshot_plugin sp where sp.preset_id=pp.id)").fetchone()[0]
    ok = db.execute("pragma integrity_check").fetchone()[0]
    db.close()
    return ok == "ok" and bad == 0
