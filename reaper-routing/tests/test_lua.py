import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
LUA_SCRIPTS = sorted(SCRIPTS.glob("*.lua"))
REQUIRED = os.environ.get("REQUIRE_LUA") == "1"


def find(*names):
    return next((shutil.which(n) for n in names if shutil.which(n)), None)


class Lua(unittest.TestCase):
    def need(self, tool):
        if tool:
            return tool
        if REQUIRED:
            self.fail("REQUIRE_LUA=1 but no Lua interpreter / compiler is installed")
        self.skipTest("Lua not installed")

    def test_compiles(self):
        luac = self.need(find("luac5.4", "luac", "luac5.5"))
        for script in LUA_SCRIPTS:
            subprocess.run([luac, "-p", str(script)], check=True)

    def test_reascript_suite(self):
        lua = self.need(find("lua5.4", "lua", "lua5.5"))
        r = subprocess.run([lua, str(SKILL / "tests" / "lua" / "run.lua")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"\d+ tests, 0 failed")

    def test_uses_only_reaper_calls_listed_in_reference(self):
        text = "".join(p.read_text(encoding="utf-8") for p in LUA_SCRIPTS)
        reference = (SKILL / "reference" / "rpp-format.md").read_text(encoding="utf-8")
        for call in sorted(set(re.findall(r"reaper\.(\w+)", text))):
            self.assertIn(f"`{call}`", reference, f"reaper.{call} is not in reference/rpp-format.md")
        for call in sorted(set(re.findall(r"gfx\.(\w+)", text))):
            self.assertIn(f"`gfx.{call}`", reference, f"gfx.{call} is not in reference/rpp-format.md")

    def test_delete_is_off_by_default(self):
        self.assertIn("local delete_files, scroll = false, 0", (SCRIPTS / "cleanup_silent_takes.lua").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
