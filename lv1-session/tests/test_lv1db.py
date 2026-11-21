import sqlite3
import tempfile
import unittest
from pathlib import Path

import fixtures
import lv1db


class SendSuffix(unittest.TestCase):
    def test_fx_slots(self):
        self.assertEqual([lv1db.send_suffix("fx", i) for i in (0, 7)], ["0", "7"])

    def test_mon_slots(self):
        self.assertEqual(lv1db.send_suffix("mon", 0), "8")
        self.assertEqual(lv1db.send_suffix("mon", 7), "15")
        self.assertEqual(lv1db.send_suffix("mon", 8), "2_0")
        self.assertEqual(lv1db.send_suffix("mon", 15), "2_7")
        self.assertEqual(lv1db.send_suffix("mon", 16), "3_0")


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = fixtures.make_session(Path(self.tmp.name) / "s.emo")


    def test_clean_session(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        self.assertEqual(lv1db.check(db.cursor()), ("ok", 0))

    def test_wrong_ref_count_is_reported(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        db.execute("update plugin_preset set ref_count = ref_count + 1 where id = 1")
        self.assertEqual(lv1db.check(db.cursor())[1], 1)

    def test_open_ro_cannot_write(self):
        db = lv1db.open_ro(self.path)
        self.addCleanup(db.close)
        with self.assertRaises(sqlite3.OperationalError):
            db.execute("update user_keys set key_action = 1")


if __name__ == "__main__":
    unittest.main()
