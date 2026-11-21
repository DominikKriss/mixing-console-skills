import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import T_INPUT, T_MATRIX, T_MON, T_TB
import edit_lv1_session
import rack


class Edit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.src = fixtures.make_session(self.dir / "src.emo", snaps=(-1, 0))
        self.dst = str(self.dir / "out.emo")
        self.src_s = fixtures.Session(self.src)
        self.addCleanup(self.src_s.close)
        self.addCleanup(self.src_s.close)


    def edit(self, edits):
        path = self.dir / "edits.json"
        path.write_text(json.dumps(edits), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            edit_lv1_session.main(self.src, self.dst, str(path))
        self.s = fixtures.Session(self.dst)
        self.addCleanup(self.s.close)
        self.addCleanup(self.s.close)
        return out.getvalue()

    def test_output_ends_with_integrity(self):
        out = self.edit({"names": {"mon": {"1": "axA"}}})
        self.assertIn("integrity: ok, presets with wrong ref_count: 0", out)
        self.assertEqual(self.s.name(T_MON, 0), "axA")

    def test_copy_mon_bus(self):
        db = self.src_s.db
        mon1 = self.src_s.oid(T_MON, 0)
        rack.set_stereo(db.cursor(), mon1, [-1, 0])
        db.execute("update chainer set is_input_nx=1 where obj_id=?", (mon1,))
        fixtures.add_plug(db.cursor(), mon1, 3, "EMO-IEM", "IEMS", fixtures.chunk("EMO-IEM", "IEMS", [1, 2]), [-1, 0])
        db.commit()
        self.edit({"copy_bus": [{"type": "mon", "from": 1, "to": [2, 3]}]})
        for i in (1, 2):
            self.assertEqual(self.s.rack(T_MON, i), self.s.rack(T_MON, 0))
            self.assertEqual(self.s.width(T_MON, i), (2, 1))
        self.assertTrue(fixtures.ref_counts_ok(self.dst))

    def test_copy_matrix_resets_target_source_levels(self):
        self.src_s.set_param(T_MATRIX, 0, "PARAM_INPUT_MATRIX_GAIN_0", 0.0)
        self.src_s.set_param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_1", 0.0, snaps=(-1, 0))
        self.edit({"copy_bus": [{"type": "matrix", "from": 1, "to": [2]}]})
        self.assertEqual(self.s.param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_0"), 0.0)
        for snap in (-1, 0):
            self.assertIsNone(self.s.param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_1", snap))

    def test_nx_positions_copied_and_defaults_reset(self):
        self.src_s.set_param(T_INPUT, 0, "PARAM_AUX_SEND_ROTATE_NX_8", 30.0)
        self.src_s.set_param(T_INPUT, 1, "PARAM_AUX_SEND_ROTATE_NX_9", 45.0)
        self.edit({"copy_bus": [{"type": "mon", "from": 1, "to": [2], "nx_positions": True}]})
        self.assertEqual(self.s.param(T_INPUT, 0, "PARAM_AUX_SEND_ROTATE_NX_9"), 30.0)
        self.assertIsNone(self.s.param(T_INPUT, 1, "PARAM_AUX_SEND_ROTATE_NX_9"))

    def test_add_plugin(self):
        self.edit({"add_plugin": [{"from": {"type": "matrix", "index": 1, "slot": 1},
                                   "to": {"type": "matrix", "index": [2]}, "slot": 5}]})
        self.assertIn((4, "EMO-F2", "CFLM"), self.s.rack(T_MATRIX, 1))
        self.assertTrue(fixtures.ref_counts_ok(self.dst))

    def test_add_plugin_needs_a_free_slot(self):
        with self.assertRaises(SystemExit):
            self.edit({"add_plugin": [{"from": {"type": "matrix", "index": 1, "slot": 1},
                                       "to": {"type": "matrix", "index": [2]}, "slot": 1}]})

    def test_add_plugin_refuses_a_width_mismatch(self):
        self.src_s.db.execute("update chainer set num_inputs=2 where obj_id=?", (self.src_s.oid(T_MATRIX, 2),))
        self.src_s.db.commit()
        with self.assertRaises(SystemExit):
            self.edit({"add_plugin": [{"from": {"type": "matrix", "index": 1, "slot": 1},
                                       "to": {"type": "matrix", "index": [3]}, "slot": 5}]})

    def test_matrix_gain(self):
        self.edit({"matrix_gain": {"matrices": [1, 2], "db": -3.0}})
        self.assertEqual(self.s.param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_0", 0), -3.0)

    def test_talkback_presets_and_keys(self):
        self.edit({"talkback": {"presets": [{"name": "TB FOH", "mons": [4]}, {"name": "TB BAND", "mons": [1, 2]}]},
                   "user_keys": [{"key": 1, "sof_mon": 1}, {"key": 13, "talkback": "TB BAND"},
                                 {"key": 2, "clear": True}]})
        xml = self.s.db.execute("select preset from talk_back_specific_data").fetchone()[0]
        self.assertEqual(xml.count("<TB_Preset "), 8)
        on = self.s.pid["PARAM_AUX_SEND_ONOFF_8"]
        self.assertIn(f'<Param ID="{on}" State="1" />', xml.split('<TB_Preset ID="1">')[1])
        self.assertEqual(self.s.param(T_TB, 0, "PARAM_OUTPUT_GAIN"), 0.0)
        keys = dict((k, rest) for k, *rest in self.s.db.execute(
            "select key_index, key_action, selection_index, obj_type, obj_index from user_keys"))
        self.assertEqual(keys[0], [27, 0, 25, 0])
        self.assertEqual(keys[12], [25, 2, -1, -1])
        self.assertEqual(keys[1][0], 0)

    def test_talkback_key_needs_talkback_edit(self):
        with self.assertRaises(SystemExit):
            self.edit({"user_keys": [{"key": 13, "talkback": "TB BAND"}]})

    def test_copy_matrix_levels_per_snapshot(self):
        self.src_s.set_param(T_MATRIX, 0, "PARAM_INPUT_MATRIX_GAIN_0", -144.0, snaps=(-1,))
        self.src_s.set_param(T_MATRIX, 0, "PARAM_INPUT_MATRIX_GAIN_0", 0.0, snaps=(0,))
        self.src_s.set_param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_0", -6.0, snaps=(-1, 0))
        self.edit({"copy_bus": [{"type": "matrix", "from": 1, "to": [2]}]})
        self.assertEqual(self.s.param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_0", -1), -144.0)
        self.assertEqual(self.s.param(T_MATRIX, 1, "PARAM_INPUT_MATRIX_GAIN_0", 0), 0.0)

if __name__ == "__main__":
    unittest.main()
