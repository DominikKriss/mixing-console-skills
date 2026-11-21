#!/usr/bin/env python3
"""Write track names from a console show to a text file, line N = track N, for the route_tracks.lua window."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_reaper import Refuse, names_from_file  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("show", help="LV1 .emo, X32 .scn, WING .snap, REAPER .rpp, .txt or .csv")
    p.add_argument("dest", help="text file to write (new file)")
    p.add_argument("--device", metavar="NAME", help="with an LV1 .emo: names from the patch to this DAW device")
    a = p.parse_args(argv)
    try:
        dest = Path(a.dest)
        if dest.exists():
            raise Refuse(f"{dest} exists; pick a new name.")
        names = names_from_file(a.show, a.device)
        if not names:
            raise Refuse("no names found.")
        broken = [n for n, v in names.items() if "\n" in v or "\r" in v]
        if broken:
            raise Refuse(f"track {broken[0]}: the name has a line break; one name per line can't hold it.")
    except (Refuse, OSError, json.JSONDecodeError, sqlite3.Error) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    last = max(names)
    try:
        with open(dest, "x", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(names.get(n, "") for n in range(1, last + 1)) + "\n")
    except OSError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(f"wrote {sum(1 for v in names.values() if v)} names for tracks 1-{last} to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
