import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

import fixtures
import build_dm7 as b

IC = "InputChannel"


class Allocate(unittest.TestCase):
    def test_stereo_pairs_start_odd(self):
        chans, nxt = b.allocate([{"name": "A", "group": "x"}, {"name": "B LR", "group": "x", "stereo": True},
                                 {"name": "C", "group": "x"}])
        self.assertEqual([c.get("name", "spare") for c in chans], ["A", "spare", "B LR", "B LR", "C"])
        self.assertEqual([c["ch"] for c in chans], [1, 2, 3, 4, 5])
        self.assertEqual(nxt, 6)

    def test_labels(self):
        self.assertEqual(b.label({"name": "KEYS LR", "half": "L"}, {}), "KEYS L")
        self.assertEqual(b.label({"name": "JULIA VOX"}, {"JULIA VOX": "JULIAVOX"}), "JULIAVOX")
        with self.assertRaises(b.Refuse):
            b.label({"name": "TOO LONG NAME"}, {})

    def test_comp_ratio(self):
        self.assertEqual(b.comp_ratio("2.5"), 25)
        self.assertEqual(b.comp_ratio("100"), 255)


class X32(unittest.TestCase):
    def setUp(self):
        self.s = fixtures.FakeSession()
        self.notes = []
        b.x32_processing(self.s, 0, fixtures.x32_channel(), self.notes, "CH 1")
        self.v = self.s.values

    def test_filters_polarity_order(self):
        self.assertEqual(self.v[(IC + "/Input", "Phase", (0, 0))], 1)
        self.assertEqual(self.v[(IC + "/HPF", "Frequency", (0, 0))], 400)
        self.assertEqual(self.v[(IC + "/HPF", "Slope", (0, 0))], 24)
        self.assertEqual(self.v[(IC + "/Proc", "EQDynOrder", (0, 0))], 1)
        self.assertEqual(self.v[(IC + "/LPF", "Frequency", (0, 0))], 120000)

    def test_gate_and_comp_words(self):
        gate = [self.v[(IC + "/Dynamics/Bank/Parameter", "Value", (0, 0, 0, j))] for j in range(5)]
        self.assertEqual(gate, [-2500, 1, -6000, 31700, 63000])
        comp = [self.v[(IC + "/Dynamics/Bank/Parameter", "Value", (0, 1, 0, j))] for j in range(6)]
        self.assertEqual(comp, [-2700, 5, 52000, 255, 2, 450])
        self.assertEqual(self.v[(IC + "/Dynamics/Bank", "Type", (0, 1, 0))], "PM Comp")
        self.assertEqual(self.v[(IC + "/Dynamics/Bank", "MixBalance", (0, 1, 0))], 80)
        self.assertEqual(self.v[(IC + "/Dynamics/KeyIn", "FilterType", (0, 0, 0))], "HPF")
        self.assertEqual(self.v[(IC + "/Dynamics/KeyIn", "FilterType", (0, 1, 0))], "NONE")
        self.assertEqual(len(self.notes), 1)

    def test_eq_shelf_last_bells_in_frequency_order(self):
        f = {k: self.v.get((IC + "/PEQ/Bank/Band", "Frequency", (0, 0, 0, k))) for k in range(4)}
        self.assertEqual(f, {0: 3000, 1: 20000, 2: None, 3: 80000})
        self.assertEqual(self.v[(IC + "/PEQ/Bank/Band", "Gain", (0, 0, 0, 2))], 0)
        self.assertEqual(self.v[(IC + "/PEQ/Bank/HighShelving", "On", (0, 0, 0, 0))], 1)
        self.assertEqual(self.v[(IC + "/PEQ/Bank/LowShelving", "On", (0, 0, 0, 0))], 0)

    def test_too_many_shelves_refused(self):
        ch = fixtures.x32_channel()
        ch["eq/1"] = ["HShv", "5k00", "+1.00", "1.0"]
        with self.assertRaises(b.Refuse):
            b.x32_processing(fixtures.FakeSession(), 0, ch, [], "CH 1")


class EqOff(unittest.TestCase):
    def test_lpf_off_when_x32_eq_off(self):
        ch = fixtures.x32_channel()
        ch["eq"] = ["OFF"]
        s = fixtures.FakeSession()
        b.x32_processing(s, 0, ch, [], "CH 1")
        self.assertEqual(s.values[(IC + "/LPF", "On", (0, 0))], 0)


class LayoutChecks(unittest.TestCase):
    LAY = {"playback_dante_start": 21, "fx_sends": [{"kind": "reverb"}, {"kind": "delay"}]}

    def test_playback_overlapping_stagebox_refused(self):
        with self.assertRaises(b.Refuse):
            b.check_layout(dict(self.LAY, playback_dante_start=20), 20, 4)

    def test_playback_right_after_stagebox_ok(self):
        b.check_layout(self.LAY, 20, 4)

    def test_duplicate_fx_kind_refused(self):
        with self.assertRaises(b.Refuse):
            b.check_layout(dict(self.LAY, fx_sends=[{"kind": "reverb"}, {"kind": "reverb"}]), 20, 4)


class Unpair(unittest.TestCase):
    def test_mono_channel_from_a_paired_base_is_unpaired(self):
        s = fixtures.FakeSession()
        b.pair(s, 1)
        b.unpair(s, 1)
        b.unpair(s, 2)
        for ch in (0, 1):
            self.assertEqual(s.values[(IC, "GainGang", (ch,))], 0)
            self.assertEqual(s.values[(IC, "DelayGang", (ch,))], 0)
            self.assertEqual(s.values[(IC + "/Signal", "Relation", (ch, 0))], 0)


class BuildUnpairs(unittest.TestCase):
    def test_two_mono_inputs_on_a_paired_base_are_unpaired_by_build(self):
        paired = {}
        for ch, rel in ((0, 128), (1, 1)):
            paired[(IC, "GainGang", (ch,))] = 1
            paired[(IC, "DelayGang", (ch,))] = 1
            paired[(IC + "/Signal", "Relation", (ch, 0))] = rel
        s = fixtures.FakeSession(paired)
        lay = {"short_names": {}, "colours": {"vox": "Yellow", "fx": "Blue", "spare": "OFF"},
               "inputs": [{"strip": "ch.1", "name": "VOX 1", "group": "vox"},
                          {"strip": "ch.2", "name": "VOX 2", "group": "vox"}],
               "dante_playback_groups": [], "tio_units": 1, "tio_inputs": 16, "playback_dante_start": 17,
               "mons": [], "fx_sends": [], "main_name": "MAIN", "matrices": [], "dante_outputs": []}
        b.build(s, lay, ".")
        for ch in (0, 1):
            self.assertEqual(s.values[(IC, "GainGang", (ch,))], 0)
            self.assertEqual(s.values[(IC, "DelayGang", (ch,))], 0)
            self.assertEqual(s.values[(IC + "/Signal", "Relation", (ch, 0))], 0)


class OutputGuard(unittest.TestCase):
    def test_output_over_base_refused_and_base_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d, "base.dmxf")
            base.write_bytes(b"not touched")
            sym, hard = Path(d, "sym.dmxf"), Path(d, "hard.dmxf")
            outs = [base, hard]
            os.link(base, hard)
            try:
                sym.symlink_to(base)
                outs.append(sym)
            except OSError:
                pass
            for out in outs:
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    self.assertEqual(b.main([str(base), "layout.json", str(out)]), 1)
                self.assertIn("not the base", buf.getvalue())
            self.assertEqual(base.read_bytes(), b"not touched")


if __name__ == "__main__":
    unittest.main()
