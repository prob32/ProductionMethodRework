# Production Method Rework — working notes

## Standing rules (Pat)

- **No extra text in the UI** (2026-10-18). A screen shows names, numbers, icons and short bullets, nothing else: no
  hint or caption lines ("Drag to move"), no intro paragraph under a header, no grey note under a value ("over the
  base method"), no bullet that restates a name or explains a mechanic. A tooltip only where a value or a lock needs
  one, at most about three short lines, with no closing line on cost or what it rules out. Before every build, scan
  new localisation for on-screen sentences and long tooltips and cut them. When in doubt, leave it out.
- **English only until finalization.** New text is written in English; the other ten languages fall back to it until
  the one translation pass before a release (`tools/pmr/localise.py --missing <language>`).
- **Every test runs in the test build**, `mod\ProductionMethodRework_QueueTest` ("PMR Test" playset), never the
  published release. Checks log on their own (`PMR;rec=` lines in debug.log), with no console steps; each run sheet
  row says what a null means.
- **Never install while the game runs.** Read the last line of `logs\debug.log` first: `DeleteAllPlayers` means
  closed.
- **One committer.** Only the build session commits to `dev` and installs on Pat's PC. Design sessions hand their work
  (specs, patches) over as files in the project's shared folder. `main` moves to `dev` at a release.
- **Public game files only.** Target Victoria 3 1.15.x. Never read the separate `Victoria 3 BETA` install.

## Building

- The mod is generated: `python3 tools/pmr/generate.py --game <Victoria 3 install>/game --out <dir>`, with
  `--test-name "Queue Test"` for the test build or `--release` for the Workshop build. Never hand-edit or commit
  generated files.
- Every performance and design switch is off by default, so a build without the switch list is an old build. The
  current release and test command lines are in the build handoff (`/mnt/project-files/pmr/build/HANDOFF.md`).
- The run sheet is `pmr/RUNSHEET.md`, newest build first. The design as built is `pmr/README.md`.
