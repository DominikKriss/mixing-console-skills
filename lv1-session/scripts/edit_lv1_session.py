#!/usr/bin/env python3
"""Apply edits (JSON) to a copy of an LV1 .emo session the user already edited in LV1.

Usage: edit_lv1_session.py <source.emo> <output.emo> <edits.json>

Edits, applied in this order (all optional, bus numbers 1-based):
  names         {"mon": {"16": "axTB FOH"}, "matrix": {...}, "fx": {...}, "input": {...}}
  copy_bus      [{"type": "mon"|"matrix", "from": 1, "to": [2, 3], "nx_positions": true}]
                Rack (plugins, presets, bypass), mono/stereo, Nx type (Mon), matrix source levels and
                assignment type (Matrix). nx_positions (Mon): every input's Nx rotate / width in the
                source mix is copied to the target mixes.
  add_plugin    [{"from": {"type": "cue", "index": 1, "slot": 4}, "to": {"type": "matrix", "index": [1, 2]},
                  "slot": 7}]  (rack slots 1-based; the target slot must be free)
  matrix_gain   {"matrices": [1, 2], "db": 0.0}  level of each matrix's first source
  talkback      {"presets": [{"name": "TB FOH", "mons": [16]}, {"name": "TB BAND", "mons": [1, 2]}],
                 "master_db": 0.0, "send_db": 0.0}
  user_keys     [{"key": 1, "sof_mon": 1}, {"key": 13, "talkback": "TB FOH"}, {"key": 5, "clear": true}]
                (keys 1-16; "talkback" names a preset from the talkback edit)
"""
import json
import shutil
import sqlite3
import sys

from lv1db import T, check, send_suffix

KEY_SOF, KEY_TALKBACK, KEY_NONE = 27, 25, 0
UNNAMED_TB_IDS = range(727, 735)


class Session:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.cur = self.db.cursor()
        self.pid = dict(self.cur.execute("select name, id from chainer_params"))
        self.obj = {(t, i): oid for oid, t, i in self.cur.execute("select id, obj_type, obj_index from object")}
        self.snaps = [r[0] for r in self.cur.execute("select id from snapshot")]
        self.plug_cols = [r[1] for r in self.cur.execute("pragma table_info(plug)")][1:]
        self.sp_cols = [r[1] for r in self.cur.execute("pragma table_info(snapshot_plugin)")][1:]

    def oid(self, kind, n):
        return self.obj[(T[kind], n - 1)]

    def name(self, chainer):
        return self.cur.execute("select name from snapshot_chainer where chainer_id=? and snapshot_id=-1",
                                (chainer,)).fetchone()[0]

    def set_param(self, chainer, name, value):
        for s in self.snaps:
            self.cur.execute("insert or replace into snapshot_chainer_params values (?,?,?,?)",
                             (chainer, s, self.pid[name], float(value)))

    def copy_plug(self, plug_id, chainer, slot=None, reset_window=False):
        row = dict(zip(self.plug_cols, self.cur.execute(
            f"select {','.join(self.plug_cols)} from plug where id=?", (plug_id,)).fetchone()))
        row["chainer_id"] = chainer
        if slot is not None:
            row["slot"] = slot
        self.cur.execute(f"insert into plug ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
        new = self.cur.lastrowid
        for sp in self.cur.execute(f"select {','.join(self.sp_cols)} from snapshot_plugin where plug_id=?",
                                   (plug_id,)).fetchall():
            s = dict(zip(self.sp_cols, sp))
            s["plug_id"] = new
            if reset_window:
                s.update(fw_posx=-9999, fw_posy=-9999, fw_scale_precentage=-1)
            self.cur.execute(f"insert into snapshot_plugin ({','.join(s)}) values ({','.join('?' * len(s))})",
                             list(s.values()))

    def clear_rack(self, chainer):
        for (p,) in self.cur.execute("select id from plug where chainer_id=?", (chainer,)).fetchall():
            for t in ("hot_plug", "midi_learn"):
                if self.cur.execute(f"select count(*) from {t} where plug_id=?", (p,)).fetchone()[0]:
                    sys.exit(f"{self.name(chainer)}: plugin {p} is used in {t}; not replacing the rack")
            self.cur.execute("delete from plug_sidechain where plug_id=?", (p,))
            self.cur.execute("delete from snapshot_plugin where plug_id=?", (p,))
            self.cur.execute("delete from plug where id=?", (p,))

    def copy_rack(self, src, dst):
        plugs = [r[0] for r in self.cur.execute("select id from plug where chainer_id=? order by slot", (src,))]
        self.clear_rack(dst)
        for p in plugs:
            self.copy_plug(p, dst)


def copy_bus(s, e):
    kind = e["type"]
    src = s.oid(kind, e["from"])
    width, nx = s.cur.execute("select num_inputs, is_input_nx from chainer where obj_id=?", (src,)).fetchone()
    for n in e["to"]:
        dst = s.oid(kind, n)
        s.copy_rack(src, dst)
        s.cur.execute("update chainer set num_inputs=? where obj_id=?", (width, dst))
        if kind == "mon":
            s.cur.execute("update chainer set is_input_nx=? where obj_id=?", (nx, dst))
        if kind == "matrix":
            matrix_params = "(select id from chainer_params where name like 'PARAM_INPUT_MATRIX_%')"
            s.cur.execute(f"delete from snapshot_chainer_params where chainer_id=? and param_id in {matrix_params}",
                          (dst,))
            s.cur.execute("insert into snapshot_chainer_params select ?, snapshot_id, param_id, param_value from"
                          f" snapshot_chainer_params where chainer_id=? and param_id in {matrix_params}", (dst, src))
            asgn = s.cur.execute("select src_asgn_type from snapshot_assignment where dst_id=? and dst_section_index=0"
                                 " and snapshot_id=-1", (src,)).fetchone()
            if asgn:
                s.cur.execute("update snapshot_assignment set src_asgn_type=? where dst_id=? and dst_section_index=0",
                              (asgn[0], dst))
        print(f"copy {kind} {e['from']} {s.name(src)} -> {n} {s.name(dst)}")
    if kind == "mon" and e.get("nx_positions"):
        sfx = send_suffix("mon", e["from"] - 1)
        rows = s.cur.execute(
            "select v.chainer_id, v.snapshot_id, cp.name, v.param_value from snapshot_chainer_params v"
            " join chainer_params cp on cp.id=v.param_id where cp.name in (?, ?)",
            (f"PARAM_AUX_SEND_ROTATE_NX_{sfx}", f"PARAM_AUX_SEND_WIDTH_NX_{sfx}")).fetchall()
        for n in e["to"]:
            dsfx = send_suffix("mon", n - 1)
            s.cur.execute("delete from snapshot_chainer_params where param_id in (?, ?)",
                          (s.pid[f"PARAM_AUX_SEND_ROTATE_NX_{dsfx}"], s.pid[f"PARAM_AUX_SEND_WIDTH_NX_{dsfx}"]))
            for ch, snap, name, value in rows:
                s.cur.execute("insert or replace into snapshot_chainer_params values (?,?,?,?)",
                              (ch, snap, s.pid[name[: -len(sfx)] + dsfx], value))
        print(f"nx positions: {len(rows)} values from mon {e['from']} -> {e['to']}")


def add_plugin(s, e):
    f = e["from"]
    src = s.oid(f["type"], f["index"])
    row = s.cur.execute("select id, plugin_name, plugin_4cc from plug where chainer_id=? and slot=?",
                        (src, f["slot"] - 1)).fetchone()
    if not row:
        sys.exit(f"{s.name(src)} has no plugin in slot {f['slot']}")
    to = e["to"]
    for n in to["index"]:
        dst = s.oid(to["type"], n)
        width = s.cur.execute("select num_inputs from chainer where obj_id=?", (dst,)).fetchone()[0]
        if row[2][-1:] in ("M", "S") and (row[2][-1] == "S") != (width == 2):
            sys.exit(f"{row[1]} ({row[2]}) doesn't fit {s.name(dst)}: it is {'stereo' if width == 2 else 'mono'}")
        if s.cur.execute("select count(*) from plug where chainer_id=? and slot=?", (dst, e["slot"] - 1)).fetchone()[0]:
            sys.exit(f"{s.name(dst)} slot {e['slot']} is not free")
        s.copy_plug(row[0], dst, slot=e["slot"] - 1, reset_window=True)
        print(f"add {row[1]} from {s.name(src)} slot {f['slot']} -> {s.name(dst)} slot {e['slot']}")


def matrix_gain(s, e):
    for n in e["matrices"]:
        s.set_param(s.oid("matrix", n), "PARAM_INPUT_MATRIX_GAIN_0", e.get("db", 0.0))
    print(f"matrix source level {e.get('db', 0.0)} dB: {e['matrices']}")


def talkback(s, e):
    tb = s.obj[(T["talkback"], 0)]
    names = [n for n in s.pid if n.startswith(("PARAM_AUX_SEND_ONOFF_", "PARAM_OUTPUT_ASSIGNMENT_GRUOP_",
                                               "PARAM_OUTPUT_ASSIGNMENT_MATRIX_", "PARAM_OUTPUT_ASSIGNMENT_CR_"))
             or n in ("PARAM_OUTPUT_ASSIGNMENT_LR", "PARAM_OUTPUT_ASSIGNMENT_C", "PARAM_OUTPUT_ASSIGNMENT_M")]
    ids = sorted({s.pid[n] for n in names} | {i for i in UNNAMED_TB_IDS if i not in s.pid.values()})
    presets, used = [], set()
    for p in e["presets"]:
        on = {s.pid[f"PARAM_AUX_SEND_ONOFF_{send_suffix('mon', m - 1)}"] for m in p.get("mons", [])}
        on |= {s.pid[f"PARAM_AUX_SEND_ONOFF_{send_suffix('fx', f - 1)}"] for f in p.get("fx", [])}
        used |= on
        rows = "".join(f'  <Param ID="{i}" State="{int(i in on)}" />\n' for i in ids)
        presets.append(f' <TB_Preset ID="{len(presets)}">\n{rows} </TB_Preset>\n')
    if len(presets) > 8:
        sys.exit("LV1 has 8 talkback presets")
    xml = "<TB_Presets>\n" + "".join(presets) + "".join(
        f' <TB_Preset ID="{n}" />\n' for n in range(len(presets), 8)) + "</TB_Presets>\n"
    s.cur.execute("update talk_back_specific_data set preset=? where chainer_id=?", (xml, tb))
    s.set_param(tb, "PARAM_OUTPUT_GAIN", e.get("master_db", 0.0))
    id_name = {v: k for k, v in s.pid.items()}
    for i in used:
        s.set_param(tb, id_name[i].replace("ONOFF", "GAIN"), e.get("send_db", 0.0))
    s.tb_presets = [p["name"] for p in e["presets"]]
    print(f"talkback presets: {s.tb_presets}")


def user_keys(s, e):
    for k in e:
        idx = k["key"] - 1
        if "sof_mon" in k:
            vals = (KEY_SOF, 0, T["mon"], k["sof_mon"] - 1, k.get("label", ""))
        elif "talkback" in k:
            vals = (KEY_TALKBACK, s.tb_presets.index(k["talkback"]) + 1, -1, -1, k.get("label", k["talkback"]))
        elif k.get("clear"):
            vals = (KEY_NONE, -1, -1, -1, "")
        else:
            sys.exit(f"user key {k['key']}: need sof_mon, talkback or clear")
        s.cur.execute("update user_keys set key_action=?, selection_index=?, obj_type=?, obj_index=?,"
                      " uk_friendly_name=? where key_index=?", (*vals, idx))
        if not s.cur.rowcount:
            sys.exit(f"user key {k['key']} not in session")
    print(f"user keys: {[k['key'] for k in e]}")


def main(src, dst, edits_path):
    e = json.load(open(edits_path, encoding="utf-8"))
    if "user_keys" in e and any("talkback" in k for k in e["user_keys"]) and "talkback" not in e:
        sys.exit("talkback user keys need the talkback edit in the same file")
    shutil.copyfile(src, dst)
    s = Session(dst)
    try:
        apply_edits(s, e)
        s.db.commit()
        ok, bad = check(s.cur)
    finally:
        s.db.close()
    print(f"wrote {dst}, integrity: {ok}, presets with wrong ref_count: {bad}")


def apply_edits(s, e):
    for kind, objs in e.get("names", {}).items():
        for n, name in objs.items():
            s.cur.execute("update snapshot_chainer set name=? where chainer_id=?", (name, s.oid(kind, int(n))))
    for c in e.get("copy_bus", []):
        copy_bus(s, c)
    for a in e.get("add_plugin", []):
        add_plugin(s, a)
    if "matrix_gain" in e:
        matrix_gain(s, e["matrix_gain"])
    if "talkback" in e:
        talkback(s, e["talkback"])
    if "user_keys" in e:
        user_keys(s, e["user_keys"])


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
