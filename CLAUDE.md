# Production Method Rework — working notes

## No extra text in the UI (Pat, 2026-10-18 21:53Z and 22:28Z)

Never add explainer lines or extra tooltips. A screen shows names, numbers, icons and short bullets, nothing else:

- no hint or caption lines ("Choose a founding culture", "Drag to move"), intro paragraphs under a header, or grey notes
  under a value ("over the base method", "Earning nothing while its prosperity is 0");
- no bullets that restate the node's name or explain the mechanic ("• Investment charter", "• Opens the outer half",
  "• Then: unlocked for retooling and new builds");
- tooltips only where a value or a lock needs one, at most about three short lines, with no closing line on cost, arm or
  what rules it out.

Before every build, scan new localisation for sentences shown on screen or tooltips longer than a few lines, and cut
them. When in doubt, leave it out.

## Building

- The mod is generated: `python3 tools/pmr/generate.py --game <Victoria 3 install> --out <dir>` (`--release` for the
  published build, `--test-name "Queue Test"` for the test build). Never hand-edit generated files.
- Target Victoria 3 1.15.x only.
- English only until finalization: new text goes in English; the other ten languages fall back to it.
- Every test runs in the test build (`mod\ProductionMethodRework_QueueTest`, "PMR Test" playset), never the published
  release. Checks log on their own (`PMR;rec=` lines in debug.log); the run sheet is `pmr/RUNSHEET.md`.
