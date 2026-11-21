import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "cleanup_silent_takes.lua"


class LuaSyntax(unittest.TestCase):
    def test_compiles(self):
        luac = next((shutil.which(c) for c in ("luac", "luac5.4", "luac5.3") if shutil.which(c)), None)
        if not luac:
            self.skipTest("no luac installed")
        subprocess.run([luac, "-p", str(SCRIPT)], check=True)

    def test_uses_only_reaper_calls_listed_in_reference(self):
        text = SCRIPT.read_text(encoding="utf-8")
        reference = (SCRIPT.parent.parent / "reference" / "rpp-format.md").read_text(encoding="utf-8")
        import re
        for call in sorted(set(re.findall(r"reaper\.(\w+)", text))):
            self.assertIn(call, reference, f"reaper.{call} is not in reference/rpp-format.md")


if __name__ == "__main__":
    unittest.main()
