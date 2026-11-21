"""Stereo input channels and fixed plugin racks for LV1 .emo sessions.

eMo F2 / D5 / Q4 already sit on every channel and are only moved. Other plugins are copied
(plug row metadata + preset chunk) from a donor session the user saved with that plugin in use.
"""
import hashlib
import re
import sqlite3

from lv1db import open_ro

EMO = {"EMO-F2": ("CFLM", "CFLS"), "EMO-D5": ("CDYM", "CDYS"), "EMO-Q4": ("MQ4M", "MQ4S")}
PARAMS_RE = re.compile(r'(<Parameters Type="RealWorld">)(.*?)(</Parameters>)', re.S)


def store_preset(cur, chunk):
    h = hashlib.sha3_256(chunk.encode()).hexdigest()
    row = cur.execute("select id from plugin_preset where hash=?", (h,)).fetchone()
    if row:
        return row[0]
    cur.execute("insert into plugin_preset (hash, ref_count, preset) values (?,0,?)", (h, chunk))
    return cur.lastrowid


def default_preset(cur, subcomp):
    """Most-used preset of a plugin variant in this session (the stock default in a fresh session)."""
    row = cur.execute("select id from plugin_preset where preset like ? order by ref_count desc limit 1",
                      (f"%<PluginSubComp>{subcomp}</PluginSubComp>%",)).fetchone()
    if not row:
        raise SystemExit(f"no {subcomp} preset in the source session to use as a template")
    return row[0]


def override(chunk, values):
    """values: {token_index: value} applied in every <Parameters> block."""
    def repl(m):
        toks = m.group(2).split()
        for i, v in values.items():
            toks[int(i)] = str(v)
        lines = [" ".join(toks[i:i + 10]) for i in range(0, len(toks), 10)]
        return m.group(1) + "\n" + "\n".join(lines) + "\n" + m.group(3)
    return PARAMS_RE.sub(repl, chunk)


def set_stereo(cur, chainer, snaps):
    """Make an input stereo: chainer width 2, eMo plugins switched to their stereo variant at default."""
    cur.execute("update chainer set num_inputs=2 where obj_id=?", (chainer,))
    for name, (mono, st) in EMO.items():
        for (plug,) in cur.execute("select id from plug where chainer_id=? and plugin_name=?",
                                   (chainer, name)).fetchall():
            cur.execute("update plug set plugin_4cc=? where id=?", (st, plug))
            pid = default_preset(cur, st)
            for s in snaps:
                cur.execute("update snapshot_plugin set preset_id=? where plug_id=? and snapshot_id=?", (pid, plug, s))


def set_mono(cur, chainer, snaps):
    """Make a channel mono: width 1, stereo eMo variants switched back to the mono variant at default."""
    cur.execute("update chainer set num_inputs=1 where obj_id=?", (chainer,))
    for name, (mono, st) in EMO.items():
        for (plug,) in cur.execute("select id from plug where chainer_id=? and plugin_name=? and plugin_4cc=?",
                                   (chainer, name, st)).fetchall():
            cur.execute("update plug set plugin_4cc=? where id=?", (mono, plug))
            pid = default_preset(cur, mono)
            for s in snaps:
                cur.execute("update snapshot_plugin set preset_id=? where plug_id=? and snapshot_id=?", (pid, plug, s))


class Donor:
    """Read-only view of a saved session to copy plugins from."""

    def __init__(self, path):
        self.db = open_ro(path)
        self.chan = {n: cid for cid, n in self.db.execute(
            "select o.id, sc.name from object o join snapshot_chainer sc on sc.chainer_id=o.id"
            " where o.obj_type=0 and sc.snapshot_id=-1")}

    def close(self):
        self.db.close()

    def plugin(self, channel, plugin_name):
        """(plug row dict, Active preset chunk) of plugin_name on the donor channel, or None."""
        cid = self.chan.get(channel)
        if cid is None:
            raise SystemExit(f"donor has no input named {channel!r}")
        cols = [d[1] for d in self.db.execute("pragma table_info(plug)")]
        row = self.db.execute("select * from plug where chainer_id=? and plugin_name=?", (cid, plugin_name)).fetchone()
        if not row:
            return None
        plug = dict(zip(cols, row))
        chunk = self.db.execute(
            "select pp.preset from snapshot_plugin sp join plugin_preset pp on pp.id=sp.preset_id"
            " where sp.plug_id=? and sp.snapshot_id=-1", (plug["id"],)).fetchone()[0]
        return plug, chunk


def build_rack(cur, chainer, stereo, slots, donor, donor_cfg, input_name, snaps):
    """slots: {ui_slot (1-based): plugin_name}. Moves eMo plugins, removes everything else, adds donor plugins.

    Returns a list of report notes.
    """
    notes = []
    want = {int(k) - 1: v for k, v in slots.items()}
    twice = sorted({n for n in want.values() if n in EMO and list(want.values()).count(n) > 1})
    if twice:
        raise SystemExit(f"{input_name}: {', '.join(twice)} listed in more than one slot; each channel has one")
    rows = cur.execute("select id, plugin_name from plug where chainer_id=? order by slot", (chainer,)).fetchall()
    existing = {}
    for pid, name in rows:
        if name in EMO and name in want.values() and name not in existing:
            existing[name] = pid
    drop = [pid for pid, name in rows if existing.get(name) != pid]
    for pid in drop:
        for t in ("hot_plug", "midi_learn"):
            if cur.execute(f"select count(*) from {t} where plug_id=?", (pid,)).fetchone()[0]:
                raise SystemExit(f"{input_name}: plugin {pid} is used in {t}; not replacing the rack")
    for pid in drop:
        cur.execute("delete from snapshot_plugin where plug_id=?", (pid,))
        cur.execute("delete from plug_sidechain where plug_id=?", (pid,))
        cur.execute("delete from plug where id=?", (pid,))
    for name, pid in existing.items():
        cur.execute("update plug set slot=? where id=?", (-100 - pid, pid))
    width = "stereo" if stereo else "mono"
    for slot, name in sorted(want.items()):
        if name in EMO:
            if name not in existing:
                raise SystemExit(f"{input_name}: {name} missing from the source session")
            cur.execute("update plug set slot=? where id=?", (slot, existing[name]))
            continue
        cfg = donor_cfg.get(name, {})
        src = cfg.get("channels", {}).get(input_name)
        found = donor.plugin(src, name) if src else None
        if found and (found[0]["plugin_4cc"][-1] == "S") != stereo:
            notes.append(f"{name} from {src} is {'stereo' if not stereo else 'mono'}, used {width} default")
            found = None
        if not found:
            src = cfg["default"][width]
            found = donor.plugin(src, name)
            if not found:
                raise SystemExit(f"donor channel {src!r} has no {name}")
        plug, chunk = found
        if cfg.get("override"):
            chunk = override(chunk, cfg["override"])
        pid = store_preset(cur, chunk)
        cur.execute(
            "insert into plug (chainer_id, slot, plugin_name, plugin_4cc, additional_info, disabled, recall_safe,"
            " side_chain, hot_plugin, vendor_name, plug_role, ignore_latency) values (?,?,?,?,?,0,0,0,-1,?,0,0)",
            (chainer, slot, name, plug["plugin_4cc"], plug["additional_info"], plug["vendor_name"]))
        new_plug = cur.lastrowid
        for s in snaps:
            cur.execute("insert into snapshot_plugin (plug_id, preset_id, snapshot_id, setup_type_id, bypass, mute,"
                        " docked) values (?,?,?,-1,0,0,1)", (new_plug, pid, s))
        notes.append(f"{name}<-{src}")
    return notes
