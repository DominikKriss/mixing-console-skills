#!/usr/bin/env python3
"""Readable diff of two LV1 .emo sessions (Active state), objects by type and number: names, bus width / Nx type, parameters,
plugin racks (name, variant, preset hash, bypass), assignments (Matrix sources), patching, user keys, talkback presets.

Usage: diff_lv1_sessions.py <a.emo> <b.emo>
"""
import re
import sys

from lv1db import open_ro


def load(path):
    c = open_ro(path)
    try:
        return _load(c)
    finally:
        c.close()


def _load(c):
    ct = dict(c.execute("select id, name from cluster_type"))
    names = dict(c.execute("select chainer_id, name from snapshot_chainer where snapshot_id=-1"))
    objs = {oid: f"{ct.get(t, t)} {i + 1}" for oid, t, i in c.execute("select id, obj_type, obj_index from object")}
    pn = dict(c.execute("select id, name from chainer_params"))
    d = {"name": {objs[o]: n for o, n in names.items() if o in objs},
         "bus": {}, "param": {}, "plug": {}, "route": set(), "key": {}, "tb": None, "asgn": {}}
    for src, sec, dst, idx, at in c.execute("select src_id, src_section_type, dst_id, dst_section_index, src_asgn_type"
                                            " from snapshot_assignment where snapshot_id=-1"):
        d["asgn"][(objs.get(dst, dst), idx)] = (objs.get(src, src), sec, at)
    for oid, w, nx in c.execute("select obj_id, num_inputs, is_input_nx from chainer"):
        d["bus"][objs.get(oid, oid)] = (w, nx)
    for ch, p, v in c.execute("select chainer_id, param_id, param_value from snapshot_chainer_params"
                              " where snapshot_id=-1"):
        d["param"][(objs.get(ch, ch), pn.get(p, p))] = v
    for ch, slot, name, cc, h, byp in c.execute(
            "select p.chainer_id, p.slot, p.plugin_name, p.plugin_4cc, pp.hash, sp.bypass from plug p"
            " left join snapshot_plugin sp on sp.plug_id=p.id and sp.snapshot_id=-1"
            " left join plugin_preset pp on pp.id=sp.preset_id"):
        d["plug"][(objs.get(ch, ch), slot + 1)] = f"{name}/{cc} {(h or '')[:8]}{' BYPASS' if byp else ''}"
    cols = [r[1] for r in c.execute("pragma table_info(routes)")][1:]
    for r in c.execute(f"select {','.join(cols)} from routes"):
        d["route"].add(r)
    for r in c.execute("select key_index, key_action, selection_index, obj_type, obj_index, uk_friendly_name"
                       " from user_keys"):
        d["key"][r[0] + 1] = r[1:]
    tb = c.execute("select preset from talk_back_specific_data").fetchone()
    if tb:
        d["tb"] = {pid: sorted(pn.get(int(i), i) for i in re.findall(r'Param ID="(\d+)" State="1"', body))
                   for pid, body in re.findall(r'<TB_Preset ID="(\d+)"(?: />|>(.*?)</TB_Preset>)', tb[0], re.S)}
    return d


def show(title, a, b):
    keys = sorted(set(a) | set(b), key=str)
    rows = [f"  {k}: {a.get(k)} -> {b.get(k)}" for k in keys if a.get(k) != b.get(k)]
    if rows:
        print(f"== {title}")
        print("\n".join(rows))


def main(pa, pb):
    a, b = load(pa), load(pb)
    show("names", a["name"], b["name"])
    show("bus (inputs, nx)", a["bus"], b["bus"])
    show("parameters", a["param"], b["param"])
    show("assignments (dst, slot): (src, section, asgn_type)", a["asgn"], b["asgn"])
    show("plugins (bus, rack slot)", a["plug"], b["plug"])
    show("user keys (action, selection, obj_type, obj_index, label)", a["key"], b["key"])
    if a["tb"] != b["tb"]:
        show("talkback presets (ON destinations)", a["tb"] or {}, b["tb"] or {})
    gone, new = a["route"] - b["route"], b["route"] - a["route"]
    if gone or new:
        print(f"== routes: {len(gone)} removed, {len(new)} added (src_cluster, src_idx, .., src_ch, .., dst_cluster,"
              " dst_idx, .., dst_section_idx, dst_ch, ..)")
        for r in sorted(gone):
            print("  -", r)
        for r in sorted(new):
            print("  +", r)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
