# Mixing console skills for Claude Code

Live audio mixing console skillset: [Claude Code](https://claude.com/claude-code) skills that prepare, change and review shows for the Waves eMotion LV1, Behringer WING and Yamaha DM7 by script, without clicking through every channel and bus.

Each skill reads and writes the console's own show file (LV1 `.emo` SQLite sessions, WING `.snap` JSON snapshots, DM7 `.dmxf` MBDF sessions) on top of a file the console's editor saved, and the result goes back through that editor before it reaches a desk.

## Skills

| Skill | What it does |
|---|---|
| [`lv1-session`](lv1-session/) | Build a session from a layout (inputs, IEM / monitor mixes, FX, matrices), convert Behringer X32 channel processing to eMo F2 / D5 / Q4, edit a session you already worked on (copy a mix's setup to other mixes, Nx IEM, talkback, user keys), and review what changed between two sessions. |
| [`wing-snapshot`](wing-snapshot/) | Build a WING snapshot from a layout on a WING-Edit INIT save: names, colours, AES50 / local patch with stereo sockets, monitor, group and FX buses, inserts, matrices, DCAs, output patch, and X32 channel processing. |
| [`dm7-session`](dm7-session/) | Build a DM7 session from a layout on a DM Editor 2.0.1 session: names, pairs, Dante / Tio patch, monitor and FX mixes, FX routing, matrices, Dante outputs, and X32 channel processing. |

## Install

```sh
git clone https://github.com/DominikKriss/mixing-console-skills.git ~/mixing-console-skills
mkdir -p ~/.claude/skills
for s in lv1-session wing-snapshot dm7-session; do ln -s ~/mixing-console-skills/$s ~/.claude/skills/$s; done
```

On Windows (PowerShell; Claude Code on Windows runs skills through Git Bash), use folder junctions, which need no
admin rights:

```powershell
git clone https://github.com/DominikKriss/mixing-console-skills.git $HOME\mixing-console-skills
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
foreach ($s in 'lv1-session','wing-snapshot','dm7-session') {
  New-Item -ItemType Junction -Path "$HOME\.claude\skills\$s" -Target "$HOME\mixing-console-skills\$s"
}
```

Then ask Claude Code about your show, or run `/lv1-session`, `/wing-snapshot` or `/dm7-session`. `git -C ~/mixing-console-skills pull` updates.

## Requirements

- Python 3 (standard library only) on macOS, Windows or Linux; CI runs every skill's tests on all three. On Windows, Git for Windows (Git Bash) for `contribute.sh`. LV1: tested with LV1 17.3 on macOS. WING: a snapshot from WING-Edit (tested with 3.2.1). DM7: a session from DM Editor 2.0.1 (firmware V2.01).
- The Waves plugins a skill works with installed through Waves Central (see each skill's README).

## Caution

Unofficial; not affiliated with or supported by Waves, Behringer or Yamaha. The formats were worked out by reverse-engineering, so keep a backup of every show. Open every generated file in the console's editor (LV1, WING-Edit, DM Editor), check it, save it there, and load only that save on a desk, first at prep, never at the show. For LV1: load an edited session before saving anything, or LV1 writes the old in-memory state over it.

## Contributing

**Mixing on a console that isn't here yet?** Your desk is welcome: Allen & Heath, DiGiCo, Midas, Soundcraft, Yamaha CL / QL / RIVAGE, X32 itself, anything with an offline editor. Start small (names and patch from an input list is already useful), open a [new console request](https://github.com/DominikKriss/mixing-console-skills/issues/new?template=new_console.yml) to say you're on it, and see [Adding a console](CONTRIBUTING.md#adding-a-console).

**Found a bug or a value the editor showed differently? Please report it**: [open an issue](https://github.com/DominikKriss/mixing-console-skills/issues/new/choose) or a pull request, for any skill. See [CONTRIBUTING.md](CONTRIBUTING.md); agents read [AGENTS.md](AGENTS.md). Editor load results and format findings (one change made in the editor, diffed between two saves) are the most useful contributions.

The skills learn from use: when a run turns up something the skill should know (a fix, a format finding, a missing rule), Claude Code offers to open a pull request with it from your GitHub account. It shows the account, commit email and files first and only opens the PR if you say yes.

## License

[GPL-3.0](LICENSE). Waves, eMotion LV1 and SoundGrid are trademarks of Waves Audio Ltd.; Behringer, X32 and WING are trademarks of Music Tribe; Yamaha, DM7 and Tio are trademarks of Yamaha Corporation. `dm7-session/vendor/yamaha_tool.py` is MIT-licensed (show-file-skills, see its licence file). They are named only to describe compatibility.
