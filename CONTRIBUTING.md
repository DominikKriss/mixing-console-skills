# Contributing

Found a bug, a wrong value, or something the editor showed differently? Please tell us: every report makes the skills better for the next engineer. Issues and pull requests are welcome for every skill (`lv1-session`, `wing-snapshot`, `dm7-session`). `main` is protected: every change goes through a pull request; CodeRabbit must approve it (it requests changes on actionable findings and approves once they are resolved) and the maintainer merges.

The quickest route: open an issue with the [bug report](https://github.com/DominikKriss/mixing-console-skills/issues/new?template=bug_report.yml) or [format finding](https://github.com/DominikKriss/mixing-console-skills/issues/new?template=format_finding.yml) form. If you use Claude Code, it offers to open the pull request for you after a run that taught a skill something.

## Reporting a problem

Open an issue with:

- the skill, and the console / editor version (LV1 and Session Editor, WING-Edit, DM Editor), firmware, OS
- the command you ran and its full output
- what the editor showed after loading the result, and what you expected

Don't attach your show files (`.emo`, `.snap`, `.dmxf`, `.dm7f`, `.scn`) unless you're happy for them to be public: they contain your channel names, patching and device names.

## Reporting a session-format finding

Most of this skill comes from comparing two saved sessions that differ by one change made in LV1. If you find a field that isn't in a skill's format reference (e.g. [lv1-session/reference/emo-format.md](lv1-session/reference/emo-format.md)):

1. Save a session, make one change in LV1 (one key, one bus, one plugin), save it under a new name.
2. Run `python3 lv1-session/scripts/diff_lv1_sessions.py before.emo after.emo`.
3. Open an issue or a pull request with the diff output, what you changed in LV1, and your LV1 version.

## Adding a console

New consoles are the contribution we'd love most. You don't need to cover everything: a skill that writes names, colours and patch from an input list, loads cleanly in the console's editor and is honest about what it doesn't do is a great first pull request. The rest can follow, one proven field at a time.

1. **Open a [new console request](https://github.com/DominikKriss/mixing-console-skills/issues/new?template=new_console.yml)** with the console, its editor and firmware, and what you plan to write first, so nobody duplicates work.
2. **Start from an editor save.** Make an empty show in the console's offline editor and decode it: save, change one thing, save again, diff. Write each finding in `reference/` with how it was proven.
3. **Copy the shape of an existing skill:** `wing-snapshot/` (JSON format) or `dm7-session/` (binary format with a vendored reader) is a good template. One folder, `SKILL.md`, README, `scripts/`, `examples/` (synthetic), `reference/`, `tests/`, and a copy of `lv1-session/scripts/contribute.sh` (CI checks the copies match). Rules for agents and people alike are in [AGENTS.md](AGENTS.md).
4. **Reuse what exists.** The X32 scene reader (`wing-snapshot/scripts/x32_to_wing.py`, `dm7-session/scripts/x32_scn.py`) can be copied to convert X32 processing to your desk. Existing open-source decoders are welcome as vendored code if their licence allows it (MIT, BSD, GPL-compatible), kept unchanged with their licence file; [show-file-skills](https://github.com/michaelkeithlewis/show-file-skills) has format notes for many desks.
5. **Prove it in the editor:** in the PR, say which editor version loaded the generated file and what it showed. Add a row to the README skills table.

Questions while you work? Open a draft pull request early; the maintainer is happy to help.

## Decisions and issues

Work is tracked in [GitHub issues](https://github.com/DominikKriss/mixing-console-skills/issues), labelled by type and skill. Decisions that affect more than one skill, or that a contributor would trip over, are recorded as [ADRs](docs/adr/README.md): copy `docs/adr/template.md`, add a row to the index, and propose it in your pull request with status `Proposed`.

## Branch names

Open or pick an issue first, then branch from `main` as `feature/<issue>_<short-desc>` (or `fix/<issue>_<short-desc>` for a bug), e.g. `feature/8_windows-support`, and put `Closes #<issue>` in the pull request. The short description is lowercase and uses only `a-z`, `0-9`, `-`, `.` and `_`, starting with a letter or digit (`feature/8_Add-console` is rejected). CI checks the branch name. Pull requests opened by Claude Code's `contribute.sh` use `learn/...` branches and are exempt.

## Pull requests

The easiest way: after a run that taught a skill something, Claude Code offers to open the pull request for you (`<skill>/scripts/contribute.sh`, the same script in every skill, which needs the GitHub CLI logged in). It forks the repo to your account and commits only the skill folder; check the dry-run output for the commit email you want to publish.

- One topic per pull request. Update the skill's `SKILL.md` and format reference along with the scripts. A new skill goes in its own folder with a `SKILL.md`, a README and a row in the repository README.
- Python 3 standard library only.
- Add or update the tests in the skill's `tests/` folder (`python3 -m unittest discover -s tests -t tests` from the skill folder). Tests use synthetic sessions from `tests/fixtures.py`, never a real `.emo`. GitHub Actions runs them on every pull request.
- Test on a copy of a real show and include in the PR (LV1):
  - the script output, ending with `integrity: ok` and `presets with wrong ref_count: 0`
  - the `diff_lv1_sessions.py` output before → after
  - confirmation that LV1 loaded the result and showed the change
- Never commit show files (`.emo`, `.snap`, `.dmxf`, `.dm7f`, `.scn`; `.gitignore` blocks them). For WING and DM7, include the builder output and what the editor (WING-Edit, DM Editor) showed after loading the result.

By contributing you agree that your contribution is licensed under the [GPL-3.0](LICENSE).
