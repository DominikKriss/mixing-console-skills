import sqlite3
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import T_INPUT
import rack

Q10_VALUES = list(range(110))


class Override(unittest.TestCase):
    def test_tokens_replaced_in_every_block(self):
        out = rack.override(fixtures.chunk("Q10", "EQ1M", Q10_VALUES), {"102": 3, "103": 4})
        blocks = out.split('<Parameters Type="RealWorld">')[1:]
        self.assertEqual(len(blocks), 2)
        for b in blocks:
            toks = b.split("</Parameters>")[0].split()
            self.assertEqual(toks[102:104], ["3", "4"])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.path = fixtures.make_session(self.dir / "s.emo", snaps=(-1, 0))
        self.donor = fixtures.make_session(self.dir / "donor.emo", inputs=2)
        db = sqlite3.connect(self.donor)
        self.addCleanup(db.close)
        cur = db.cursor()
        ids = [r[0] for r in cur.execute("select id from object where obj_type=0 order by obj_index")]
        fixtures.add_plug(cur, ids[0], 3, "Q10", "EQ1M", fixtures.chunk("Q10", "EQ1M", Q10_VALUES), [-1])
        fixtures.add_plug(cur, ids[1], 3, "Q10", "EQ1S", fixtures.chunk("Q10", "EQ1S", Q10_VALUES), [-1])
        db.commit()
        db.close()
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.cur = self.db.cursor()
        self.chainer = self.cur.execute("select id from object where obj_type=0 and obj_index=0").fetchone()[0]

    def tearDown(self):
        self.db.close()

    def rack(self):
        self.db.commit()
        s = fixtures.Session(self.path)
        self.addCleanup(s.close)
        r = s.rack(T_INPUT, 0)
        s.close()
        return r


class SetStereo(Base):
    def test_width_and_stereo_variants(self):
        rack.set_stereo(self.cur, self.chainer, [-1, 0])
        self.assertEqual(self.cur.execute("select num_inputs from chainer where obj_id=?", (self.chainer,)).fetchone(),
                         (2,))
        self.assertEqual({cc for _s, _n, cc in self.rack()}, {"CFLS", "CDYS", "MQ4S"})
        self.assertTrue(fixtures.ref_counts_ok(self.path))


class SetMono(Base):
    def test_back_to_mono_variants(self):
        rack.set_stereo(self.cur, self.chainer, [-1, 0])
        rack.set_mono(self.cur, self.chainer, [-1, 0])
        self.assertEqual(self.cur.execute("select num_inputs from chainer where obj_id=?", (self.chainer,)).fetchone(),
                         (1,))
        self.assertEqual({cc for _s, _n, cc in self.rack()}, {"CFLM", "CDYM", "MQ4M"})
        self.assertTrue(fixtures.ref_counts_ok(self.path))


class BuildRack(Base):
    CFG = {"Q10": {"default": {"mono": "IN 1", "stereo": "IN 2"}, "override": {"102": 7, "103": 7}}}

    def _donor(self):
        d = rack.Donor(self.donor)
        self.addCleanup(d.close)
        return d

    def build(self, slots, stereo=False, cfg=None):
        return rack.build_rack(self.cur, self.chainer, stereo, slots, self._donor(), cfg or self.CFG,
                               "IN 1", [-1, 0])

    def test_emo_moved_donor_plugin_added(self):
        notes = self.build({"1": "EMO-F2", "2": "EMO-Q4", "3": "EMO-D5", "8": "Q10"})
        self.assertEqual(self.rack(), [(0, "EMO-F2", "CFLM"), (1, "EMO-Q4", "MQ4M"), (2, "EMO-D5", "CDYM"),
                                       (7, "Q10", "EQ1M")])
        self.assertEqual(notes, ["Q10<-IN 1"])
        s = fixtures.Session(self.path)
        self.addCleanup(s.close)
        text = s.preset(T_INPUT, 0, "Q10", snap=0)
        s.close()
        self.assertIn("7 7", text)
        self.assertTrue(fixtures.ref_counts_ok(self.path))

    def test_unlisted_plugins_removed(self):
        self.build({"1": "EMO-F2", "2": "EMO-Q4"})
        self.assertEqual([n for _s, n, _c in self.rack()], ["EMO-F2", "EMO-Q4"])
        self.assertTrue(fixtures.ref_counts_ok(self.path))

    def test_donor_width_mismatch_uses_default(self):
        cfg = {"Q10": {"channels": {"IN 1": "IN 2"}, "default": {"mono": "IN 1", "stereo": "IN 2"}}}
        notes = self.build({"1": "EMO-F2", "4": "Q10"}, cfg=cfg)
        self.assertIn("used mono default", notes[0])

    def test_same_emo_in_two_slots_is_refused(self):
        with self.assertRaises(SystemExit):
            self.build({"1": "EMO-D5", "3": "EMO-D5"})

    def test_every_instance_of_an_unlisted_plugin_is_removed(self):
        fixtures.add_plug(self.cur, self.chainer, 5, "EMO-D5", "CDYM", fixtures.chunk("EMO-D5", "CDYM"), [-1, 0],
                          role=1)
        self.build({"1": "EMO-Q4"})
        self.assertEqual([n for _s, n, _c in self.rack()], ["EMO-Q4"])
        self.assertTrue(fixtures.ref_counts_ok(self.path))

    def test_plugin_used_by_hot_plug_is_not_removed(self):
        d5 = self.cur.execute("select id from plug where chainer_id=? and plugin_name='EMO-D5'",
                              (self.chainer,)).fetchone()[0]
        self.cur.execute("insert into hot_plug values (1, ?)", (d5,))
        with self.assertRaises(SystemExit):
            self.build({"1": "EMO-Q4"})

class SecondD5(Base):
    def test_every_d5_instance_changes_width(self):
        fixtures.add_plug(self.cur, self.chainer, 5, "EMO-D5", "CDYM", fixtures.chunk("EMO-D5", "CDYM"), [-1, 0],
                          role=1)
        rack.set_stereo(self.cur, self.chainer, [-1, 0])
        self.assertEqual([cc for _s, n, cc in self.rack() if n == "EMO-D5"], ["CDYS", "CDYS"])
        rack.set_mono(self.cur, self.chainer, [-1, 0])
        self.assertEqual([cc for _s, n, cc in self.rack() if n == "EMO-D5"], ["CDYM", "CDYM"])
        self.assertTrue(fixtures.ref_counts_ok(self.path))

if __name__ == "__main__":
    unittest.main()
