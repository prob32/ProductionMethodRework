# Production Method Rework

Production Method Rework (PMR) is a script-only mod for Victoria 3 1.15. Research no longer upgrades a building
overnight. Each level retools to the new recipe through construction, and a building's output is the blend of the
recipes its levels run. Companies also gain a culture tree, a board and subsidiaries.

The mod is on the [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3819399957). It needs no
other mods.

## Building the mod

The mod is generated, not written by hand. `tools/pmr/generate.py` reads the installed game's own script and writes
the whole mod folder, so a new game version only needs a new run. The generated folder is not committed.

```
python3 tools/pmr/generate.py --game "<Victoria 3 install>/game" --release
```

- `--release` writes the Workshop build to `pmr/release/ProductionMethodRework`.
- Without `--release`, it writes a test build with extra logging to `pmr/ProductionMethodRework`.
- The generator needs Python 3 with Pillow and numpy, and the game's full English localisation.

Copy the generated folder into `Documents\Paradox Interactive\Victoria 3\mod\` and enable it in a playset.

## Repository

| Path | Contents |
| --- | --- |
| `tools/pmr/` | The generator, its modules and the translation tables. |
| `pmr/README.md` | The design as built, with the decision behind each part. |
| `pmr/RUNSHEET.md` | The in-game checks for each test build. |
| `pmr/test_probes/` | Small test mods used while building features. |

`main` holds the latest Workshop release. `dev` is the working branch and can be ahead of it.

## Releases

| Version | Commit | Workshop upload |
| --- | --- | --- |
| 0.1.0 | `81c609a` | 2026-10-13 |
| 0.2.0 | `aee27c9` | 2026-10-14 |
| 0.3.0 | `1d21176` | 2026-10-20 |
| 0.3.1 | `6b6b809` | 2026-10-22 |
| 0.3.2 | `f4ef573` | 2026-10-23 |
| 0.4.0 | `27c230c` | 2026-11-06 |

## Feedback

Report bugs as GitHub issues or in the Workshop comments. Include your game version, the in-game date and your mod
list.
