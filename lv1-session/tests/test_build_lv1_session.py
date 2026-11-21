import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import T_FX, T_INPUT, T_MATRIX, T_MON
import build_lv1_session
import rack

LAYOUT = {
    "inputs": ["KICK", {"name": "KEYS", "stereo": True}, "VOX", "TB"],
    "mons": [{"name": "axA", "stereo": True, "matrix": 1, "own": ["VOX"]},
             {"name": "axB", "own": ["KICK"]},
             {"name": "SPARE", "sends": False}],
    "levels": {"other_db": -10.0, "own_db": 0.0},
    "always_pre_0db": ["TB"],
    "fx": [{"name": "REV", "feeds": {"VOX": [-5.0, "PST"]}, "dedicated_to": "axA"}],
    "fx_returns": {"own_db": -6.0, "other_db": -15.0},
    "colors": [{"value": 4, "inputs": ["KICK"], "mons": [1]}],
    "x32_to_lv1": {"1": 1},
}


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        os.environ["LV1_EMO_PARAMXML_DIR"] = str(fixtures.write_paramxml(self.dir / "paramxml"))
        self.src = fixtures.make_session(self.dir / "src.emo")
        self.dst = str(self.dir / "out.emo")

    def tearDown(self):
        os.environ.pop("LV1_EMO_PARAMXML_DIR", None)

    def build(self, layout=LAYOUT, scene=None):
        path = self.dir / "layout.json"
        path.write_text(json.dumps(layout), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            build_lv1_session.main(self.src, self.dst, str(path), scene)
        self.s = fixtures.Session(self.dst)
        self.addCleanup(self.s.close)
        self.addCleanup(self.s.close)
        return out.getvalue()

    def send(self, t, i, mon, what="GAIN"):
        return self.s.param(t, i, f"PARAM_AUX_SEND_{what}_{8 + mon}")

    def test_output_ends_with_integrity(self):
        out = self.build()
        self.assertIn("integrity: ok", out)
        self.assertIn("presets with wrong ref_count: 0", out)
        self.assertTrue(fixtures.ref_counts_ok(self.dst))

    def test_source_is_not_written(self):
        before = Path(self.src).read_bytes()
        self.build()
        self.assertEqual(Path(self.src).read_bytes(), before)

    def test_names(self):
        self.build()
        self.assertEqual([self.s.name(T_INPUT, i) for i in range(4)], ["KICK", "KEYS", "VOX", "TB"])
        self.assertEqual(self.s.name(T_MON, 0), "axA")
        self.assertEqual(self.s.name(T_MATRIX, 0), "axA")
        self.assertEqual(self.s.name(T_FX, 0), "REV")

    def test_monitor_sends(self):
        self.build()
        self.assertEqual((self.send(T_INPUT, 0, 0), self.send(T_INPUT, 0, 0, "SOURCE")), (-10.0, 3.0))
        self.assertEqual((self.send(T_INPUT, 2, 0), self.send(T_INPUT, 2, 0, "SOURCE")), (0.0, 1.0))
        self.assertEqual((self.send(T_INPUT, 0, 1), self.send(T_INPUT, 0, 1, "SOURCE")), (0.0, 1.0))
        self.assertEqual(self.send(T_INPUT, 3, 1), 0.0)
        self.assertEqual(self.send(T_INPUT, 0, 0, "ONOFF"), 1.0)
        self.assertIsNone(self.send(T_INPUT, 0, 2))

    def test_fx_sends_and_dedicated_returns(self):
        self.build()
        self.assertEqual(self.s.param(T_INPUT, 2, "PARAM_AUX_SEND_GAIN_0"), -5.0)
        self.assertEqual(self.s.param(T_INPUT, 2, "PARAM_AUX_SEND_SOURCE_0"), 2.0)
        self.assertEqual(self.s.param(T_INPUT, 0, "PARAM_AUX_SEND_ONOFF_0"), 0.0)
        self.assertEqual(self.send(T_FX, 0, 0), -6.0)
        self.assertEqual(self.send(T_FX, 0, 1), -15.0)

    def test_stereo_mon_and_matrix(self):
        self.build()
        self.assertEqual(self.s.width(T_MON, 0)[0], 2)
        self.assertEqual({cc for _s, _n, cc in self.s.rack(T_MON, 0)}, {"CFLS", "CDYS", "MQ4S"})
        self.assertEqual(self.s.width(T_MATRIX, 0)[0], 2)
        self.assertEqual(self.s.param(T_MATRIX, 0, "PARAM_INPUT_MATRIX_GAIN_0"), 0.0)
        row = self.s.db.execute("select src_id, src_asgn_type from snapshot_assignment where dst_id=?",
                                (self.s.oid(T_MATRIX, 0),)).fetchone()
        self.assertEqual(row, (self.s.oid(T_MON, 0), 1))

    def test_stereo_input_and_colour(self):
        self.build()
        self.assertEqual(self.s.width(T_INPUT, 1)[0], 2)
        self.assertEqual(self.s.param(T_INPUT, 0, "PARAM_COLOR_VALUE"), 4.0)
        self.assertEqual(self.s.param(T_MON, 0, "PARAM_COLOR_VALUE"), 4.0)

    def test_mono_layout_input_on_a_stereo_source_input(self):
        db = sqlite3.connect(self.src)
        self.addCleanup(db.close)
        oid = db.execute("select id from object where obj_type=0 and obj_index=0").fetchone()[0]
        rack.set_stereo(db.cursor(), oid, [-1])
        db.commit()
        db.close()
        self.build()
        self.assertEqual(self.s.width(T_INPUT, 0)[0], 1)
        self.assertEqual({cc for _s, _n, cc in self.s.rack(T_INPUT, 0)}, {"CFLM", "CDYM", "MQ4M"})

    def test_unknown_names_exit(self):
        layout = dict(LAYOUT, always_pre_0db=["NOPE"])
        with self.assertRaises(SystemExit):
            self.build(layout)

    def test_x32_scene(self):
        scene = fixtures.write_scene(self.dir / "s.scn", {1: {"name": "KICK", "hp": ("ON", "80")}})
        out = self.build(scene=scene)
        self.assertIn("X32 ch 1 KICK -> LV1 ch 1", out)
        self.assertEqual(self.s.preset_values(T_INPUT, 0, "EMO-F2")["PARAM_L_HPF_ON"], "1")

    def test_command_line(self):
        path = self.dir / "layout.json"
        path.write_text(json.dumps(LAYOUT), encoding="utf-8")
        script = fixtures.SCRIPTS / "build_lv1_session.py"
        r = subprocess.run([sys.executable, str(script), self.src, self.dst, str(path)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("integrity: ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
