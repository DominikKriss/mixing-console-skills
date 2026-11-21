"""Shared helpers for LV1 .emo sessions (SQLite)."""
import sqlite3
from pathlib import Path

T = {"input": 0, "group": 1, "fx": 2, "matrix": 6, "cue": 7, "talkback": 8, "mon": 25}


def open_ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?immutable=1", uri=True)


def send_suffix(kind, index):
    """0-based index. FX n -> n; Mon 1-8 -> 8-15, Mon 9-16 -> 2_0-7, Mon 17-24 -> 3_0-7."""
    if kind == "fx":
        return str(index)
    if index < 8:
        return str(8 + index)
    return f"{2 + (index - 8) // 8}_{(index - 8) % 8}"


def check(cur):
    """(integrity, presets whose ref_count differs from their snapshot_plugin rows)."""
    ok = cur.execute("pragma integrity_check").fetchone()[0]
    bad = cur.execute("select count(*) from plugin_preset pp where ref_count !="
                      " (select count(*) from snapshot_plugin sp where sp.preset_id=pp.id)").fetchone()[0]
    return ok, bad
