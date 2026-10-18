# Production Method Rework

A script-only Victoria 3 mod for 1.14 ([Steam Workshop 3819399957](https://steamcommunity.com/sharedfiles/filedetails/?id=3819399957)).
The mod folder is generated from the installed game by `tools/pmr/generate.py`; see `pmr/README.md` for the
design, the build and the test handover in `pmr/RUNSHEET.md`.

## Branches

- `dev` is the one working branch. Fixes land here and go through the test build first.
- `main` moves to `dev` when a release is uploaded.

## Releases

| Version | Commit | Workshop upload |
| --- | --- | --- |
| 0.1.0 | `81c609a` | 2026-10-13 |
| 0.2.0 | `aee27c9` | 2026-10-14 |

Feedback from the Workshop page is tracked as issues labelled `feedback`.

History before this repository is PMR's commits from Ironroad's `claude/pmr-mod-p71kui` branch, filtered to
`tools/pmr/` and `pmr/`, so commit ids differ from Ironroad's.
