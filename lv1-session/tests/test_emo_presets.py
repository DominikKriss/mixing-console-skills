import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import T_INPUT
import emo_presets as ep


class Helpers(unittest.TestCase):
    def test_place_eq_keeps_frequency_order_within_slot_limits(self):
        slots, dropped = ep.place_eq([("LCut", 100.0, 0.0, 1.0), ("PEQ", 1000.0, 3.0, 2.0),
                                      ("HShv", 8000.0, 2.0, 1.0), ("PEQ", 500.0, 0.0, 1.0)])
        self.assertEqual(slots[1][0], "HighPass")
        self.assertEqual(slots[2][0], "Bell")
        self.assertEqual(slots[3][0], "HighShelf")
        self.assertEqual(dropped, [])

    def test_place_eq_drops_what_does_not_fit(self):
        slots, dropped = ep.place_eq([("LCut", 80.0, 0.0, 1.0), ("LShv", 200.0, 2.0, 1.0),
                                      ("LShv", 300.0, 4.0, 1.0), ("HCut", 12000.0, 0.0, 1.0)])
        self.assertEqual(len(slots) + len(dropped), 4)
        self.assertTrue(dropped)

    def test_knee_mapping(self):
        scene = {0: "Hard", 2: "Normal", 4: "Soft"}
        for x32, emo in scene.items():
            lines = fixtures.x32_channel(1, dyn={"on": "ON", "knee": str(x32)})
            c = {ln.split()[0][7:]: ln.split()[1:] for ln in lines}
            self.assertEqual(ep.x32_settings(c)["comp"]["knee"], emo)

    def test_build_chunk_refuses_display_only_and_wrong_length(self):
        names = fixtures.F2
        template = fixtures.chunk("EMO-F2", "CFLM")
        with self.assertRaises(ValueError):
            ep.build_chunk(template, names, {"PARAM_IN_VU_L": 1})
        with self.assertRaises(ValueError):
            ep.build_chunk(template, names[:-1], {})
        out = ep.build_chunk(template, names, {"PARAM_L_HPF_ON": 1, "PARAM_L_HPF_FREQ": 80.5})
        self.assertEqual(out.count("1 80.5"), 2)


def settings(**kw):
    s = {"trim": 0.0, "invert": False, "hp": None, "eq": {}, "eq_dropped": [], "gate": None, "comp": None,
         "comp_post_eq": False}
    s.update(kw)
    return s


class Q4Values(unittest.TestCase):
    def test_unused_bands_are_switched_off(self):
        v = ep.q4_values(settings(eq={2: ("Bell", 1000.0, 3.0, 2.0)}))
        self.assertEqual(v["PARAM_BAND2_STATE_L"], 1)
        for name in ("PARAM_BAND_STATE", "PARAM_BAND1_STATE_R", "PARAM_BAND3_STATE_L", "PARAM_BAND4_STATE_R"):
            self.assertEqual(v[name], 0, name)

    def test_output_gain_written_when_no_extra_trim(self):
        v = ep.q4_values(settings(trim=5.0))
        self.assertEqual((v["PARAM_OUT_GAIN_L"], v["PARAM_OUT_GAIN_R"]), (0.0, 0.0))

    def test_trim_above_ten_goes_to_output_gain(self):
        self.assertEqual(ep.q4_values(settings(trim=18.0))["PARAM_OUT_GAIN_L"], 8.0)


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        os.environ["LV1_EMO_PARAMXML_DIR"] = str(fixtures.write_paramxml(self.dir / "paramxml"))
        self.path = fixtures.make_session(self.dir / "s.emo", snaps=(-1, 0))

    def tearDown(self):
        os.environ.pop("LV1_EMO_PARAMXML_DIR", None)

    def apply(self, **channel):
        scene = fixtures.write_scene(self.dir / "s.scn", {1: {"name": "KICK", **channel}})
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        s = fixtures.Session(self.path)
        self.addCleanup(s.close)
        report = ep.apply(db.cursor(), {0: s.oid(T_INPUT, 0)}, scene, {1: 0}, [-1, 0])
        db.commit()
        db.close()
        s.close()
        return report

    def session(self):
        s = fixtures.Session(self.path)
        self.addCleanup(s.close)
        return s

    def order(self):
        s = self.session()
        names = [n for _slot, n, _cc in s.rack(T_INPUT, 0)]
        s.close()
        return names

    def test_settings_written_to_every_snapshot(self):
        self.apply(hp=("ON", "80"), trim="+18.0", inv="ON", gate={"on": "ON"})
        s = self.session()
        for snap in (-1, 0):
            self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-F2", snap)["PARAM_L_HPF_ON"], "1")
            self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-D5", snap)["PARAM_GATE_ON"], "1")
            self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-Q4", snap)["PARAM_OUT_GAIN_L"], "8")
            self.assertEqual(s.param(T_INPUT, 0, "PARAM_INPUT_DIGITAL_TRIM_L", snap), 10.0)
            self.assertEqual(s.param(T_INPUT, 0, "PARAM_INPUT_PHASE_ONOFF_R", snap), 1.0)
        s.close()
        self.assertTrue(fixtures.ref_counts_ok(self.path))

    def test_post_eq_compressor_sets_order(self):
        self.apply(dyn={"on": "ON"}, dyn_pos="POST")
        self.assertEqual(self.order(), ["EMO-F2", "EMO-Q4", "EMO-D5"])

    def test_order_is_set_not_toggled_on_a_rebuild(self):
        self.apply(dyn={"on": "ON"}, dyn_pos="POST")
        self.apply(dyn={"on": "ON"}, dyn_pos="POST")
        self.assertEqual(self.order(), ["EMO-F2", "EMO-Q4", "EMO-D5"])
        self.apply(dyn={"on": "ON"}, dyn_pos="PRE")
        self.assertEqual(self.order(), ["EMO-F2", "EMO-D5", "EMO-Q4"])

    def test_rebuild_clears_eq_bands_the_new_scene_does_not_use(self):
        self.apply(eq_on="ON", eq=[("PEQ", "1k00", "+3.00", "2.0")])
        s = self.session()
        self.assertIn("1", [v for k, v in s.preset_values(T_INPUT, 0, "EMO-Q4").items() if "STATE" in k])
        s.close()
        self.apply(eq_on="OFF")
        s = self.session()
        self.assertEqual({v for k, v in s.preset_values(T_INPUT, 0, "EMO-Q4").items() if "STATE" in k}, {"0"})
        s.close()

    def test_rebuild_resets_q4_output_gain(self):
        self.apply(trim="+18.0")
        self.apply(trim="+0.0")
        s = self.session()
        self.assertEqual(float(s.preset_values(T_INPUT, 0, "EMO-Q4")["PARAM_OUT_GAIN_L"]), 0.0)
        s.close()

    def test_missing_emo_plugin_is_reported_not_a_crash(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        f2 = db.execute("select id from plug where plugin_name='EMO-F2' and chainer_id="
                        "(select id from object where obj_type=0 and obj_index=0)").fetchone()[0]
        db.execute("delete from snapshot_plugin where plug_id=?", (f2,))
        db.execute("delete from plug where id=?", (f2,))
        db.commit()
        db.close()
        report = self.apply(hp=("ON", "80"), gate={"on": "ON"})
        self.assertIn("EMO-F2 not in the rack", report[0])
        s = self.session()
        self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-D5")["PARAM_GATE_ON"], "1")
        s.close()

    def test_trim_above_ten_without_q4_reports_the_missing_gain(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        q4 = db.execute("select id from plug where plugin_name='EMO-Q4' and chainer_id="
                        "(select id from object where obj_type=0 and obj_index=0)").fetchone()[0]
        db.execute("delete from snapshot_plugin where plug_id=?", (q4,))
        db.execute("delete from plug where id=?", (q4,))
        db.commit()
        db.close()
        report = self.apply(trim="+18.0")
        self.assertIn("+8.0 dB missing", report[0])
        self.assertNotIn("Q4 out", report[0])

    def test_gate_modes_other_than_gate_are_not_converted(self):
        report = self.apply(gate={"on": "ON"}, gate_mode="DUCK")
        self.assertIn("gate mode DUCK not converted", report[0])
        s = self.session()
        self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-D5")["PARAM_GATE_ON"], "0")
        s.close()

    def test_expander_is_not_converted_to_a_compressor(self):
        report = self.apply(dyn={"on": "ON"}, dyn_mode="EXP")
        self.assertIn("dynamics mode EXP not converted", report[0])
        s = self.session()
        self.assertEqual(s.preset_values(T_INPUT, 0, "EMO-D5")["PARAM_COMP_ON"], "0")
        s.close()

    def test_d5_before_q4_keeps_the_x32_drive(self):
        report = self.apply(trim="+18.0", dyn={"on": "ON", "thr": "-20.0"}, gate={"on": "ON", "thr": "-40.0"})
        s = self.session()
        d5 = s.preset_values(T_INPUT, 0, "EMO-D5")
        s.close()
        self.assertEqual((float(d5["PARAM_COMP_THRESH"]), float(d5["PARAM_GATE_THRESH"])), (-28.0, -48.0))
        self.assertIn("D5 thresholds -8.0 dB", report[0])

    def test_d5_after_q4_keeps_the_x32_thresholds(self):
        report = self.apply(trim="+18.0", dyn={"on": "ON", "thr": "-20.0"}, dyn_pos="POST")
        s = self.session()
        self.assertEqual(float(s.preset_values(T_INPUT, 0, "EMO-D5")["PARAM_COMP_THRESH"]), -20.0)
        s.close()
        self.assertNotIn("D5 thresholds", report[0])

    def test_bypassed_plugin_is_reported_and_left_bypassed(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        db.execute("update snapshot_plugin set bypass=1 where plug_id=(select id from plug where plugin_name="
                   "'EMO-Q4' and chainer_id=(select id from object where obj_type=0 and obj_index=0))")
        db.commit()
        db.close()
        report = self.apply(eq_on="ON", eq=[("PEQ", "1k00", "+3.00", "2.0")])
        self.assertIn("EMO-Q4 is bypassed", report[0])
        s = self.session()
        self.assertEqual(s.db.execute("select count(*) from snapshot_plugin where bypass=1").fetchone()[0], 2)
        s.close()

if __name__ == "__main__":
    unittest.main()
