# Agent guide

Read this before changing anything in this repo. `CLAUDE.md` points here.

## Decisions

Read [docs/adr/](docs/adr/README.md) before changing how skills are built: one file per decision, indexed with
status and scope. A change that contradicts an accepted ADR needs a new ADR that supersedes it (keep the old one,
set its status to `Superseded by NNNN`). Work items are GitHub issues, labelled with the same scope names.

## Issues and branches

Every change starts from a GitHub issue. Create the issue first, then a branch from `main` named after it:

- `feature/<issue>_<short-desc>` for a change, e.g. `feature/8_windows-support`
- `fix/<issue>_<short-desc>` for a bug fix

The short description is lowercase: `a-z`, `0-9`, `-`, `.`, `_`, starting with a letter or digit; words joined with `-`. The pull request says `Closes #<issue>`. CI fails a pull request whose branch
doesn't match. Only `learn/...` branches from `contribute.sh` (outside contributors) are exempt, from the branch name and the
`Closes #<issue>` reference, until #11 makes contributions start from an issue too.

## Layout

One folder per skill: `lv1-session/` (Waves eMotion LV1), `wing-snapshot/` (Behringer WING), `dm7-session/`
(Yamaha DM7). Each folder is installed on its own (symlinked into `~/.claude/skills/`), so a skill never imports
from another skill's folder; shared helpers are copied (for example the X32 scene reader).

```
<skill>/
  SKILL.md        what the agent loads: when to use it, rules, layout keys
  README.md       for people: commands, status, credits
  scripts/        Python 3, standard library only
  examples/       synthetic layouts only (no real show, client or venue names)
  reference/      format notes: what the scripts rely on and how sure each item is
  tests/          unittest, synthetic fixtures in tests/fixtures.py
  vendor/         third-party code, unchanged, with its licence file
```

## Rules

- Build on a file the console's editor saved (LV1, WING-Edit, DM Editor). Change only fields that exist in it;
  refuse unknown paths with one sentence and write nothing. Never invent device IDs or plugin parameter sets.
- Write to a new file, never over the input. Every generated file goes through the editor before a desk.
- A format fact goes in the skill's `reference/` with its proof: an editor load, a controlled save (one change,
  two saves, diffed), or "unconfirmed". Don't write a guess as a fact. When a user reports an editor load, record
  it in the skill's README status with editor version and date.
- Never commit show files (`.emo`, `.snap`, `.dmxf`, `.dm7f`, `.scn`, `.rpp`); `.gitignore` blocks them and
  `contribute.sh` refuses them.
- Scripts run on macOS, Windows and Linux: open text files with `encoding="utf-8"`, close every SQLite
  connection (also on refusals; Windows locks open files), build paths with `pathlib`, keep shell scripts to what
  Git Bash has (no `rsync`, no `python3` assumption). CI runs the tests on all three.
- Tests: `PY=""; for c in python3 python; do if "$c" -c "" >/dev/null 2>&1; then PY="$c"; break; fi; done; for d in */tests; do "$PY" -m unittest discover -s "$d" -t "$d"; done` (CI runs the same, plus
  ShellCheck on `*/scripts/*.sh`). Add tests with every behaviour change. ReaScripts (`*.lua`) are tested against
  a mock of the REAPER API (`reaper-routing/tests/lua/`; from the repository root `lua reaper-routing/tests/lua/run.lua`, which finds its
  files from its own path); the unittest run calls it when
  Lua is installed, and CI installs Lua 5.4 on Linux and fails without it (`REQUIRE_LUA=1`).
- No narrative code comments; keep only short non-obvious whys. Design reasoning goes in the PR.
- `main` is protected: changes go through a pull request the maintainer reviews and merges.

## Contributions

Every skill's `SKILL.md` ends with "Learn from the run": after a run that found a bug or a format fact, the agent
offers the user a pull request through `<skill>/scripts/contribute.sh` (identical in every skill; CI compares
the copies) or an issue. Change the script in `lv1-session/scripts/` and copy it to the other skills.

## Adding a console

A new console is a new skill folder, built the way [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-console) describes.
When a user asks for a console that has no skill yet, offer to start one (an editor save as the base, names and
patch first) and to open a pull request for it.

## Vendored code

`dm7-session/vendor/yamaha_tool.py` is from show-file-skills (MIT), kept unchanged with
`vendor/LICENSE-show-file-skills`. Update it only as a whole file from upstream, noting the commit in the README.
