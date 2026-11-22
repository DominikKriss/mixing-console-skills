import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import route_reaper as rr  # noqa: E402

TRACK = """  <TRACK {{00000000-0000-0000-0000-{n:012d}}}
    NAME ""
    PEAKCOL 16576
    REC 1 {i} 1 0 0 0 0 0
    NCHAN 2
    MAINSEND 1 0
{hw}    <ITEM
      POSITION 0
      NAME {n:02d}-take.wav
      <SOURCE WAVE
        FILE "Media\\{n:02d}-take.wav"
      >
    >
  >"""


def project(count=4, hwout=(1,), nl="\r\n"):
    tracks = []
    for n in range(1, count + 1):
        hw = f"    HWOUT {1023 + n} 0 1 0 0 0 0 -1:U -1\n" if n in hwout else ""
        tracks.append(TRACK.format(n=n, i=n - 1, hw=hw))
    text = "<REAPER_PROJECT 0.1 \"7.35/win64\" 1\n  MASTERHWOUT\n" + "\n".join(tracks) + "\n>\n"
    return text.replace("\n", nl)


def track_lines(text, n):
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    t = rr.read_tracks(lines)[n - 1]
    return [lines[i].strip() for i in range(t.start, t.end) if lines[i].startswith("    ") and not lines[i].startswith("     ")]


def first(text, n, key):
    return next(ln for ln in track_lines(text, n) if ln.split()[0] == key)


class Route(unittest.TestCase):
    def test_outputs_one_to_one_mono_from_channel_1(self):
        new, _, _ = rr.route(project(), out_map=rr.parse_map(["1-4"]))
        for n in range(1, 5):
            hw = [ln for ln in track_lines(new, n) if ln.startswith("HWOUT")]
            self.assertEqual(hw, [f"HWOUT {1023 + n} 0 1 0 0 0 1024 -1:U -1"])

    def test_src_stereo_keeps_1_2_mixdown(self):
        new, _, _ = rr.route(project(), out_map={3: 9}, src_mono=False)
        self.assertEqual(first(new, 3, "HWOUT"), "HWOUT 1032 0 1 0 0 0 0 -1:U -1")

    def test_offset_map_and_stereo_pair(self):
        new, report, _ = rr.route(project(), in_map=rr.parse_map(["2-3:17"]),
                                  out_map=rr.parse_map(["2-3:33"]), stereo=[3])
        self.assertEqual(first(new, 2, "REC"), "REC 1 16 1 0 0 0 0 0")
        self.assertEqual(first(new, 3, "REC"), f"REC 1 {17 | 1024} 1 0 0 0 0 0")
        self.assertEqual(first(new, 2, "HWOUT"), f"HWOUT {32 | 1024} 0 1 0 0 0 1024 -1:U -1")
        self.assertEqual(first(new, 3, "HWOUT"), "HWOUT 33 0 1 0 0 0 0 -1:U -1")
        self.assertEqual(report[2]["in"], "18/19")
        self.assertEqual(report[2]["out"], "34/35")

    def test_master_off_and_names_quoted(self):
        new, _, _ = rr.route(project(), master=False, names={1: "OH L", 2: 'say "hi"', 3: "it's \"x\""})
        self.assertEqual(first(new, 1, "MAINSEND"), "MAINSEND 0 0")
        self.assertEqual(first(new, 1, "NAME"), 'NAME "OH L"')
        self.assertEqual(first(new, 2, "NAME"), "NAME 'say \"hi\"'")
        self.assertEqual(first(new, 3, "NAME"), "NAME `it's \"x\"`")
        self.assertEqual(first(new, 4, "NAME"), 'NAME ""')

    def test_item_lines_untouched(self):
        new, _, _ = rr.route(project(), names={1: "KICK"}, out_map={1: 1})
        self.assertIn("      NAME 01-take.wav", new)
        self.assertIn('FILE "Media\\01-take.wav"', new)

    def test_crlf_kept_and_no_change_is_identical(self):
        src = project()
        new, _, _ = rr.route(src)
        self.assertEqual(new, src)
        new, _, _ = rr.route(project(nl="\n"), master=False)
        self.assertNotIn("\r", new)

    def test_arm_disarm_monitor_keep_outs(self):
        arm = {n: True for n in range(1, 5)}
        arm[3] = False
        new, report, _ = rr.route(project(hwout=()), out_map=rr.parse_map(["1-4"]), arm=arm, monitor=0)
        self.assertEqual(first(new, 1, "REC"), "REC 1 0 0 0 0 0 0 0")
        self.assertEqual(first(new, 3, "REC"), "REC 0 2 0 0 0 0 0 0")
        self.assertEqual(sum(ln.strip().startswith("HWOUT") for ln in new.splitlines()), 4)
        self.assertEqual([r["armed"] for r in report], [True, True, False, True])
        self.assertEqual(report[0]["monitor"], "off")

    def test_arm_past_last_track_refused(self):
        with self.assertRaises(rr.Refuse):
            rr.route(project(), arm={9: True})

    def test_only_limits_tracks(self):
        new, report, _ = rr.route(project(), master=False, only=[2, 3])
        self.assertEqual(first(new, 1, "MAINSEND"), "MAINSEND 1 0")
        self.assertEqual(first(new, 2, "MAINSEND"), "MAINSEND 0 0")
        self.assertEqual([r["track"] for r in report], [2, 3])

    def test_empty_project_refused(self):
        with self.assertRaisesRegex(rr.Refuse, "no tracks"):
            rr.route("<REAPER_PROJECT 0.1\n  MASTERHWOUT\n>\n", master=False)

    def test_refusals(self):
        with self.assertRaises(rr.Refuse):
            rr.route(project(), out_map={5: 5})
        with self.assertRaises(rr.Refuse):
            rr.route(project(), out_map={1: 3, 2: 3})
        with self.assertRaises(rr.Refuse):
            rr.route(project(), out_map={1: 1, 2: 2}, stereo=[1])
        with self.assertRaises(rr.Refuse):
            rr.route(project(), in_map={1: 1024}, stereo=[1])
        with self.assertRaises(rr.Refuse):
            rr.route("<OTHER\n>\n")
        with self.assertRaises(rr.Refuse):
            rr.route(project().replace("\r\n>\r\n", "\r\n"))
        with self.assertRaises(rr.Refuse):
            rr.parse_map(["4-2"])
        with self.assertRaises(rr.Refuse):
            rr.quote("a\"b'c`")


class Names(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_lv1_emo(self):
        path = self.dir / "s.emo"
        db = sqlite3.connect(path)
        db.executescript("create table object(id, obj_type, obj_index);"
                         "create table snapshot_chainer(chainer_id, snapshot_id, name);"
                         "insert into object values (10,0,1),(11,0,0),(12,25,0);"
                         "insert into snapshot_chainer values (10,-1,'SN'),(11,-1,'KICK'),(12,-1,'MON 1'),(10,0,'old');")
        db.commit()
        db.close()
        self.assertEqual(rr.names_from_file(path), {1: "KICK", 2: "SN"})

    def emo_with_patch(self):
        path = self.dir / "p.emo"
        db = sqlite3.connect(path)
        db.executescript(
            "create table object(id, obj_type, obj_index);"
            "create table snapshot_chainer(chainer_id, snapshot_id, name);"
            "create table device(id, device_gender, mac, io_bank, assign);"
            "create table device_name(mac, gender, key, name);"
            "create table device_daw(id, hostname, is_local);"
            "create table routes(src_cluster_type, src_cluster_type_index, src_channel_index,"
            " dst_cluster_type, dst_cluster_type_index, dst_channel_index);"
            "insert into object values (10,0,0),(11,0,1),(12,0,2);"
            "insert into snapshot_chainer values (10,-1,'KICK'),(11,-1,'KEYS'),(12,-1,'SPARE');"
            "insert into device values (1,0,100,0,1),(7,1,700,1,0),(6,1,600,1,1);"
            "insert into device_name values (700,1,'k7','REC-PC'),(600,1,'k6','PLAYER');"
            "insert into device_daw values (7,'REC-PC-HOST',0),(6,'player.local',0);"
            "insert into routes values (10,1,0, 0,0,0),(10,1,4, 0,1,0),(10,1,5, 0,1,1),(10,1,5, 0,2,0),"
            "(10,1,0, 11,8,0),(10,1,4, 11,8,2),(10,1,5, 11,8,3),(10,1,9, 11,8,5),(10,1,0, 11,9,0);")
        db.commit()
        db.close()
        return path

    def test_lv1_device_patch(self):
        path = self.emo_with_patch()
        expected = {1: "KICK", 3: "KEYS L", 4: "KEYS R"}
        self.assertEqual(rr.names_from_file(path, "rec-pc"), expected)
        self.assertEqual(rr.names_from_file(path, "REC_PC_HOST"), expected)
        self.assertEqual(rr.names_from_file(path, "PLAYER"), {1: "KICK"})

    def test_lv1_device_keeps_dots(self):
        path = self.emo_with_patch()
        db = sqlite3.connect(path)
        db.execute("update device_name set name = 'REC.PC' where mac = 600")
        db.execute("update device_daw set hostname = 'other' where id = 6")
        db.commit()
        db.close()
        self.assertEqual(rr.names_from_file(path, "REC.PC"), {1: "KICK"})
        self.assertEqual(rr.names_from_file(path, "rec pc"), {1: "KICK", 3: "KEYS L", 4: "KEYS R"})

    def test_lv1_device_unknown(self):
        with self.assertRaisesRegex(rr.Refuse, "PLAYER, REC-PC"):
            rr.names_from_file(self.emo_with_patch(), "laptop")

    def test_device_needs_emo(self):
        path = self.dir / "n.txt"
        path.write_text("A\n", encoding="utf-8")
        with self.assertRaises(rr.Refuse):
            rr.names_from_file(path, "rec-pc")

    def test_x32_scn(self):
        path = self.dir / "s.scn"
        path.write_text('/ch/01/config "KICK" 1 RD 1\n/ch/02/config "OH L" 2 YE 2\n/bus/01/config "MON" 1 RD\n',
                        encoding="utf-8")
        self.assertEqual(rr.names_from_file(path), {1: "KICK", 2: "OH L"})

    def test_wing_snap(self):
        path = self.dir / "s.snap"
        path.write_text(json.dumps({"ae_data": {"ch": {"1": {"name": "KICK"}, "2": {"name": ""}}}}), encoding="utf-8")
        self.assertEqual(rr.names_from_file(path), {1: "KICK", 2: ""})

    def test_text_and_csv(self):
        (self.dir / "n.txt").write_text("KICK\nSN\n\n", encoding="utf-8")
        (self.dir / "n.csv").write_text("KICK,1\nSN,2\n", encoding="utf-8")
        self.assertEqual(rr.names_from_file(self.dir / "n.txt"), {1: "KICK", 2: "SN"})
        self.assertEqual(rr.names_from_file(self.dir / "n.csv"), {1: "KICK", 2: "SN"})

    def test_csv_quoted_comma(self):
        (self.dir / "q.csv").write_text('"Keys, lead",1\n\nBASS\n', encoding="utf-8")
        self.assertEqual(rr.names_from_file(self.dir / "q.csv"), {1: "Keys, lead", 2: "", 3: "BASS"})

    def test_rpp(self):
        path = self.dir / "old.rpp"
        src = project(3).replace('NAME ""', 'NAME "KICK"', 1).replace('NAME ""', "NAME 'say \"hi\"'", 1)
        path.write_bytes(src.encode("utf-8"))
        self.assertEqual(rr.names_from_file(path), {1: "KICK", 2: 'say "hi"', 3: ""})

    def test_unknown_suffix(self):
        with self.assertRaises(rr.Refuse):
            rr.names_from_file(self.dir / "n.xlsx")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / "p.rpp"
        self.src.write_bytes(project().encode("utf-8"))

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rr.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_writes_new_file_and_keeps_source(self):
        before = self.src.read_bytes()
        dst = self.src.with_name("p_play.rpp")
        code, out, _ = self.run_cli(self.src, dst, "--out", "1-4", "--master", "off", "--arm", "all", "--disarm", "2", "--monitor", "off")
        self.assertEqual(code, 0)
        self.assertEqual(self.src.read_bytes(), before)
        self.assertIn(b"\r\n", dst.read_bytes())
        self.assertIn("4 tracks", out)

    def test_refuses_overwrite_and_existing_dest(self):
        code, _, err = self.run_cli(self.src, self.src, "--master", "off")
        self.assertEqual(code, 1)
        self.assertIn("new file", err)
        dst = self.src.with_name("taken.rpp")
        dst.write_text("x", encoding="utf-8")
        self.assertEqual(self.run_cli(self.src, dst, "--master", "off")[0], 1)

    def test_dest_must_be_beside_source(self):
        other = Path(self.tmp.name) / "sub"
        other.mkdir()
        code, _, err = self.run_cli(self.src, other / "p2.rpp", "--master", "off")
        self.assertEqual(code, 1)
        self.assertIn("same folder", err)
        self.assertFalse((other / "p2.rpp").exists())

    def test_device_needs_names(self):
        dst = self.src.with_name("d.rpp")
        code, _, err = self.run_cli(self.src, dst, "--device", "REC-PC", "--master", "off")
        self.assertEqual(code, 1)
        self.assertIn("--names", err)
        self.assertFalse(dst.exists())

    def test_ranges(self):
        self.assertEqual(rr.ranges([1, 2, 3, 5, 7, 8]), "1-3,5,7-8")


class ExportNames(unittest.TestCase):
    def test_writes_line_per_track(self):
        import export_names
        with tempfile.TemporaryDirectory() as d:
            scn = Path(d) / "s.scn"
            scn.write_text('/ch/01/config "KICK" 1 RD 1\n/ch/03/config "OH L" 2 YE 2\n', encoding="utf-8")
            out = Path(d) / "names.txt"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(export_names.main([str(scn), str(out)]), 0)
            self.assertEqual(out.read_bytes(), b"KICK\r\n\r\nOH L\r\n")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(export_names.main([str(scn), str(out)]), 1)

    def test_multiline_name_refused(self):
        import export_names
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "n.csv"
            src.write_text('"Keys\nLead",1\nBass,2\n', encoding="utf-8")
            out = Path(d) / "names.txt"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(export_names.main([str(src), str(out)]), 1)
            self.assertIn("line break", err.getvalue())
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
