import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT = SCRIPTS / "cleanup_silent_takes.lua"
LUA = sorted(SCRIPTS.glob("*.lua"))


class LuaSyntax(unittest.TestCase):
    def test_compiles(self):
        luac = next((shutil.which(c) for c in ("luac", "luac5.4", "luac5.3") if shutil.which(c)), None)
        if not luac:
            self.skipTest("no luac installed")
        for script in LUA:
            subprocess.run([luac, "-p", str(script)], check=True)

    def test_uses_only_reaper_calls_listed_in_reference(self):
        text = "".join(p.read_text(encoding="utf-8") for p in LUA)
        reference = (SCRIPT.parent.parent / "reference" / "rpp-format.md").read_text(encoding="utf-8")
        import re
        for call in sorted(set(re.findall(r"reaper\.(\w+)", text))):
            self.assertIn(f"`{call}`", reference, f"reaper.{call} is not in reference/rpp-format.md")
        for call in sorted(set(re.findall(r"gfx\.(\w+)", text))):
            self.assertIn(f"`gfx.{call}`", reference, f"gfx.{call} is not in reference/rpp-format.md")

    def test_delete_is_off_by_default(self):
        self.assertIn("local delete_files, scroll, result = false", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
