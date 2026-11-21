#!/usr/bin/env python3
"""Set record inputs, hardware outputs, master send, names, record arm and monitoring on the tracks of a REAPER .rpp."""
import argparse
import json
import re
import shlex
import sqlite3
import sys
from pathlib import Path

MONO = 1024
STEREO_IN = 1024
MAX_CHANNEL = 1024
MONITOR = {"off": 0, "on": 1, "tape": 2}


class Refuse(Exception):
    pass


def parse_range(text):
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", text)
    if not m:
        raise Refuse(f"{text!r} is not a track number or range like 1-64.")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if a < 1 or b < a:
        raise Refuse(f"{text!r} is not a valid range (1-based, low-high).")
    return a, b


def parse_tracks(text):
    out = []
    for part in text.split(","):
        a, b = parse_range(part)
        out.extend(range(a, b + 1))
    return out


def parse_map(entries):
    """'1-40:1' -> {1: 1, ..., 40: 40}; '41-64:17' -> {41: 17, ...}. Without ':start' the map is 1:1."""
    result = {}
    for entry in entries:
        rng, _, start = entry.partition(":")
        a, b = parse_range(rng)
        first = int(start) if start else a
        if first < 1:
            raise Refuse(f"{entry!r}: channels are 1-based.")
        for i, t in enumerate(range(a, b + 1)):
            result[t] = first + i
    return result


def quote(name):
    if "\n" in name or "\r" in name:
        raise Refuse(f"track name {name!r} has a line break.")
    for q in ('"', "'", "`"):
        if q not in name:
            return f"{q}{name}{q}"
    raise Refuse(f"track name {name!r} has all three quote characters; REAPER can't store it.")


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def emo_device_names(db, device):
    rows = db.execute("select d.io_bank * 8 + d.assign, coalesce(n.name, ''), coalesce(w.hostname, '')"
                      " from device d left join device_name n on n.mac = d.mac and n.gender = d.device_gender"
                      " left join device_daw w on w.id = d.id where d.device_gender = 1").fetchall()
    match = [r[0] for r in rows if norm(device) in (norm(r[1]), norm(r[2]))]
    if len(match) != 1:
        known = ", ".join(sorted({r[1] or r[2] for r in rows})) or "none"
        raise Refuse(f"no single DAW device {device!r} in the session; DAW devices: {known}.")
    names = dict(db.execute("select o.obj_index, s.name from object o join snapshot_chainer s"
                            " on s.chainer_id = o.id and s.snapshot_id = -1 where o.obj_type = 0"))
    feeds = {}
    for lv1, dev, ch, side in db.execute(
            "select dst_cluster_type_index, src_cluster_type_index, src_channel_index, dst_channel_index"
            " from routes where src_cluster_type = 10 and dst_cluster_type = 0 order by dst_cluster_type_index"):
        feeds.setdefault((dev, ch), (lv1, side))
    stereo = {lv1 for lv1, dev, ch, side in db.execute(
        "select dst_cluster_type_index, 0, 0, max(dst_channel_index) from routes"
        " where src_cluster_type = 10 and dst_cluster_type = 0 group by dst_cluster_type_index") if side == 1}
    out = {}
    for dst, dev, ch in db.execute("select dst_channel_index, src_cluster_type_index, src_channel_index from routes"
                                   " where dst_cluster_type = 11 and dst_cluster_type_index = ? and src_cluster_type = 10",
                                   (match[0],)):
        if (dev, ch) in feeds:
            lv1, side = feeds[(dev, ch)]
            out[dst + 1] = names.get(lv1, "") + ((" R" if side else " L") if lv1 in stereo else "")
    return out


def names_from_file(path, device=None):
    path = Path(path)
    suffix = path.suffix.lower()
    if device and suffix != ".emo":
        raise Refuse("--device works with an LV1 .emo session only.")
    if suffix == ".emo":
        db = sqlite3.connect(path.resolve().as_uri() + "?immutable=1", uri=True)
        try:
            if device:
                return emo_device_names(db, device)
            rows = db.execute("select o.obj_index, s.name from object o join snapshot_chainer s"
                              " on s.chainer_id = o.id and s.snapshot_id = -1"
                              " where o.obj_type = 0 order by o.obj_index").fetchall()
        finally:
            db.close()
        return {i + 1: n for i, n in rows}
    if suffix == ".scn":
        names = {}
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"/ch/(\d+)/config\s", line)
                if m:
                    names[int(m.group(1))] = shlex.split(line)[1]
        return names
    if suffix == ".snap":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ch = data.get("ae_data", {}).get("ch", {})
        return {int(k): v["name"] for k, v in ch.items() if k.isdigit() and "name" in v}
    if suffix == ".rpp":
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        lines = text.split("\r\n" if "\r\n" in text else "\n")
        names = {}
        for t in read_tracks(lines):
            for i in t.attrs.get("NAME", [])[:1]:
                value = lines[i].strip()[4:].strip()
                if len(value) >= 2 and value[0] in "\"'`" and value[-1] == value[0]:
                    value = value[1:-1]
                names[t.number] = value
        return names
    if suffix in (".txt", ".csv", ""):
        with open(path, encoding="utf-8") as f:
            lines = [ln.rstrip("\r\n") for ln in f]
        while lines and not lines[-1].strip():
            lines.pop()
        return {i + 1: ln.split(",")[0].strip() if suffix == ".csv" else ln.strip() for i, ln in enumerate(lines)}
    raise Refuse(f"{path.name}: names come from .emo, .scn, .snap, .rpp, .txt or .csv.")


class Track:
    def __init__(self, number, start, end):
        self.number, self.start, self.end = number, start, end
        self.attrs = {}


def read_tracks(lines):
    if not lines or not lines[0].lstrip().startswith("<REAPER_PROJECT"):
        raise Refuse("not a REAPER project: the first line isn't <REAPER_PROJECT.")
    tracks, depth, cur = [], 0, None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("<"):
            depth += 1
            if depth == 2 and s.startswith("<TRACK"):
                cur = Track(len(tracks) + 1, i, None)
                tracks.append(cur)
            continue
        if s == ">":
            if depth == 2 and cur is not None:
                cur.end = i
                cur = None
            depth -= 1
            continue
        if depth == 2 and cur is not None and s:
            key = s.split(None, 1)[0]
            cur.attrs.setdefault(key, []).append(i)
    if depth != 0 or any(t.end is None for t in tracks):
        raise Refuse("the project's < > chunks don't balance; the file is cut or damaged.")
    return tracks


def route(text, *, in_map=None, out_map=None, stereo=(), master=None, names=None, arm=None,
          monitor=None, src_mono=True, only=None):
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    tracks = read_tracks(lines)
    count = len(tracks)
    stereo = set(stereo)
    for label, m in (("input", in_map or {}), ("output", out_map or {})):
        for t, ch in m.items():
            if t > count:
                raise Refuse(f"track {t} in the {label} map: the project has {count} tracks.")
            last = ch + (1 if t in stereo else 0)
            if last > MAX_CHANNEL:
                raise Refuse(f"track {t}: {label} {last} is past REAPER's {MAX_CHANNEL} channels.")
    for t in stereo:
        if t > count:
            raise Refuse(f"stereo track {t}: the project has {count} tracks.")
    selected = set(only) if only else set(range(1, count + 1))
    if max(selected) > count:
        raise Refuse(f"track {max(selected)}: the project has {count} tracks.")
    for t in arm or {}:
        if t > count:
            raise Refuse(f"track {t} to arm / disarm: the project has {count} tracks.")

    replace, insert, delete, report = {}, {}, set(), []
    taken_out = {}
    for t in tracks:
        n = t.number
        if n not in selected:
            continue
        row = {"track": n}

        def field(key):
            idx = t.attrs.get(key)
            if not idx:
                raise Refuse(f"track {n} has no {key} line; save the project in REAPER first.")
            return idx[0], lines[idx[0]].split()

        if names is not None and n in names:
            i, _ = field("NAME")
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            replace[i] = f"{indent}NAME {quote(names[n])}"
            row["name"] = names[n]

        rec_i, rec = field("REC")
        if in_map and n in in_map:
            rec[2] = str(in_map[n] - 1 + (STEREO_IN if n in stereo else 0))
        if arm and n in arm:
            rec[1] = "1" if arm[n] else "0"
        if monitor is not None:
            rec[3] = str(monitor)
        if (in_map and n in in_map) or (arm and n in arm) or monitor is not None:
            indent = lines[rec_i][: len(lines[rec_i]) - len(lines[rec_i].lstrip())]
            replace[rec_i] = indent + " ".join(rec)
        inp = int(rec[2])
        row["in"] = "-" if inp < 0 else (f"{(inp & 1023) + 1}/{(inp & 1023) + 2}" if inp & STEREO_IN else str((inp & 1023) + 1))
        row["armed"] = rec[1] == "1"
        row["monitor"] = {v: k for k, v in MONITOR.items()}.get(int(rec[3]), rec[3])

        ms_i, ms = field("MAINSEND")
        if master is not None:
            ms[1] = "1" if master else "0"
            indent = lines[ms_i][: len(lines[ms_i]) - len(lines[ms_i].lstrip())]
            replace[ms_i] = indent + " ".join(ms)
        row["master"] = ms[1] == "1"

        hw = t.attrs.get("HWOUT", [])
        outs = []
        if out_map and n in out_map:
            delete.update(hw)
            dst = out_map[n] - 1
            if n in stereo:
                dst_field, src_field, label = dst, 0, f"{dst + 1}/{dst + 2}"
            else:
                dst_field, src_field, label = dst | MONO, (MONO if src_mono else 0), str(dst + 1)
            indent = lines[ms_i][: len(lines[ms_i]) - len(lines[ms_i].lstrip())]
            hw_line = f"{indent}HWOUT {dst_field} 0 1 0 0 0 {src_field} -1:U -1"
            insert[ms_i] = [hw_line]
            outs.append(label)
            for c in ([dst, dst + 1] if n in stereo else [dst]):
                if c in taken_out:
                    raise Refuse(f"tracks {taken_out[c]} and {n} both go to hardware out {c + 1}.")
                taken_out[c] = n
        else:
            outs = [str((int(lines[i].split()[1]) & 1023) + 1) for i in hw]
        row["out"] = ",".join(outs) or "-"
        report.append(row)

    out = []
    for i, line in enumerate(lines):
        if i in delete:
            continue
        out.append(replace.get(i, line))
        out.extend(insert.get(i, []))
    return nl.join(out), report, count


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", help="the .rpp REAPER saved")
    p.add_argument("dest", help="new .rpp, in the same folder so the media paths stay valid")
    p.add_argument("--in", dest="ins", action="append", default=[], metavar="TRACKS[:FIRST]",
                   help="record inputs, e.g. 1-64 (1:1) or 41-64:17; repeatable")
    p.add_argument("--out", dest="outs", action="append", default=[], metavar="TRACKS[:FIRST]",
                   help="hardware outputs, e.g. 1-64 (1:1) or 1-8:33; repeatable")
    p.add_argument("--stereo", default="", metavar="TRACKS", help="tracks with a stereo input / output pair, e.g. 7,41-42")
    p.add_argument("--master", choices=["on", "off"], help="master / parent send")
    p.add_argument("--names", metavar="FILE", help="track names from an LV1 .emo, X32 .scn, WING .snap, another REAPER .rpp or a text list")
    p.add_argument("--device", metavar="NAME",
                   help="with an LV1 .emo: name tracks from what LV1 patched to this SoundGrid DAW device")
    p.add_argument("--arm", metavar="TRACKS|all", help="record-arm these tracks (all = every track)")
    p.add_argument("--disarm", metavar="TRACKS|all", help="disarm these tracks (applied after --arm)")
    p.add_argument("--monitor", choices=list(MONITOR), help="record monitoring on every changed track (off: no input echo)")
    p.add_argument("--only", metavar="TRACKS", help="change only these tracks, e.g. 1-40")
    p.add_argument("--src-stereo", action="store_true",
                   help="mono hardware outs take channels 1/2 mixed to mono instead of channel 1")
    a = p.parse_args(argv)
    try:
        src, dst = Path(a.source), Path(a.dest)
        if dst.resolve() == src.resolve():
            raise Refuse("write to a new file; the source stays as the backup.")
        if dst.exists():
            raise Refuse(f"{dst} exists; pick a new name.")
        with open(src, encoding="utf-8", newline="") as f:
            text = f.read()
        names = names_from_file(a.names, a.device) if a.names else None
        count_hint = len(read_tracks(text.split("\r\n" if "\r\n" in text else "\n")))
        every = list(range(1, count_hint + 1))
        arm = {}
        for spec, value in ((a.arm, True), (a.disarm, False)):
            if spec:
                for t in (every if spec == "all" else parse_tracks(spec)):
                    arm[t] = value
        new, report, count = route(
            text, in_map=parse_map(a.ins), out_map=parse_map(a.outs),
            stereo=parse_tracks(a.stereo) if a.stereo else (),
            master=None if a.master is None else a.master == "on", names=names, arm=arm,
            monitor=MONITOR.get(a.monitor), src_mono=not a.src_stereo, only=parse_tracks(a.only) if a.only else None)
    except (Refuse, OSError, json.JSONDecodeError, sqlite3.Error) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print(f"{count} tracks in {src.name}; wrote {dst}")
    print(f"{'trk':>4} {'name':<16} {'in':>6} {'out':>8} {'master':>6} {'armed':>5} {'mon':>4}")
    for r in report:
        print(f"{r['track']:>4} {r.get('name', ''):<16} {r['in']:>6} {r['out']:>8} "
              f"{'on' if r['master'] else 'off':>6} {'yes' if r['armed'] else 'no':>5} {r['monitor']:>4}")
    if a.device:
        unpatched = [n for n in range(1, count + 1) if n not in names]
        if unpatched:
            print(f"not patched to {a.device} in LV1 (candidates to disarm): {ranges(unpatched)}")
    return 0


def ranges(numbers):
    out, start, prev = [], None, None
    for n in sorted(numbers) + [None]:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if prev != start else str(start))
            start = prev = n
    return ",".join(out)


if __name__ == "__main__":
    sys.exit(main())
