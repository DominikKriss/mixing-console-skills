import contextlib
import io
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fixtures
import diff_lv1_sessions


class Diff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.a = fixtures.make_session(self.dir / "a.emo")
        self.b = str(self.dir / "b.emo")
        shutil.copyfile(self.a, self.b)


    def diff(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            diff_lv1_sessions.main(self.a, self.b)
        return out.getvalue()

    def change(self, sql, *args):
        db = sqlite3.connect(self.b)
        self.addCleanup(db.close)
        db.execute(sql, args)
        db.commit()
        db.close()

    def test_identical_sessions_print_nothing(self):
        self.assertEqual(self.diff(), "")

    def test_name_change(self):
        self.change("update snapshot_chainer set name='axA' where chainer_id="
                    "(select id from object where obj_type=25 and obj_index=0)")
        out = self.diff()
        self.assertIn("== names", out)
        self.assertIn("Mon 1: MON 1 -> axA", out)

    def test_bypass_and_user_key(self):
        self.change("update snapshot_plugin set bypass=1 where plug_id=1")
        self.change("update user_keys set key_action=27 where key_index=0")
        out = self.diff()
        self.assertIn("BYPASS", out)
        self.assertIn("== user keys", out)

    def test_parameter_change(self):
        self.change("insert into snapshot_chainer_params values ((select id from object where obj_type=0"
                    " and obj_index=0), -1, (select id from chainer_params where name='PARAM_OUTPUT_GAIN'), 0)")
        self.assertIn("('Input 1', 'PARAM_OUTPUT_GAIN'): None -> 0.0", self.diff())


if __name__ == "__main__":
    unittest.main()
