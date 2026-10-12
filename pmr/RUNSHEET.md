# PMR run sheet: Blister → Bessemer in one steel mill

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

## What each null means, decided before the run

| You see | It means | Not |
| --- | --- | --- |
| No `rec=LOADED` line | The mod is not in the playset, or `on_game_started` is not reaching appended on_actions. Check the playset first. | Anything about the design. |
| `rec=LOADED` but no `rec=INIT` lines | `pmr_state_tick` is not reaching buildings: `b:<building>` or `has_building` failed. Take **PMR test: recompute retooling now** and look again. | — |
| Switching the recipe gives no `rec=SWITCH` until the month turns | `on_production_method_changed` does not run appended on_actions. The monthly backstop still works; the switch is just seen late. | A failure of the lag. |
| `rec=SWITCH` with `queued=0`, and no **Retooling: Steel Mills** in either construction queue | The game refused to queue `building_pmr_retool_steel_mill`. This is the riskiest assumption. Look in `error.log` for the reason. | A failure of p. |
| `queued=0`, but **Retooling: Steel Mills** entries are in the queue | Script cannot see a building that is still entirely under construction, so the readback is blind until the first level lands. The queue works; watch for `retool_built=1` when it does. | A failure to queue. |
| `rec=SWITCH` with `queued=1` while `retool_total=20` | Repeated `start_building_construction` calls collapse into one queue entry. The fix is to queue one level at a time as each completes; tell me and I'll switch it. | — |
| `gov_frac=0.00` on a government-owned mill | `country_ownership_fraction` does not read government ownership; everything goes to the private queue. | — |
| Lag modifier shows on the building but the steel and iron figures match plain Bessemer after two weeks | Building-scope `goods_*_mult` from a timed modifier is not read by the economy. This kills design point 3 as written. Ironroad measured up to 12 game days before an applied modifier shows in readbacks, so wait two weeks before calling it. | — |
| A field prints as text in brackets rather than a number | A log datafunction did not resolve on this build. The instrument failed, not the mod; the other fields on the line still stand. | — |

## The run

**1. Install.** Copy `ProductionMethodRework` into `Documents\Paradox Interactive\Victoria 3\mod\`,
add it to a playset on its own, launch.

**2. Start a game as Great Britain** (any country works; GBR has spare construction). Before unpausing,
look for:

```
PMR;rec=LOADED;date=1836.1.1;hook=on_game_started
PMR;rec=INIT;...;building=building_steel_mill;from=1;to=1;level=<L>;l_start=<L>;retool_built=0;retool_total=0;p=1.000
```

There is one `rec=INIT` per treated building in the world, so expect thousands. Any steel mill line
must say `from=1;to=1`, Blister, because that is what every 1836 mill runs.

**3. Look at any steel mill's production methods.** There is a new group, **Workforce**, holding one
method, **Fixed Workforce**. Per level the building employs 500 shopkeepers, 3,500 laborers, 750
machinists and 250 engineers. The **Steelmaking Process** methods list no employment.

**4. Take the decision `PMR test: grant Bessemer and a steel mill`.** It researches Bessemer and, if
the capital has no Steel Mills, creates five levels there. Look for:

```
PMR;rec=TEST;arm=SETUP;date=...;country=Great Britain;state=Home Counties
```

If the mill was created by the decision, an `INIT` line for it follows with `level=5`.

**5. Note the capital mill's numbers on Blister,** at full staffing: per level 40 iron and 30 coal in,
65 steel out.

**6. Switch the capital mill to Bessemer Process.** Immediately, without unpausing:

```
PMR;rec=SWITCH;...;building=building_steel_mill;from=1;to=2;level=5;l_start=5;retool_built=0;retool_total=20;p=0.000;gov_frac=<f>;gov=<g>;priv=<20-g>;queued=20
PMR;rec=TICK;...;from=1;to=2;level=5;l_start=5;retool_built=0;retool_total=20;p=0.000;queued=20
```

- `retool_total=20` is N × level = 4 × 5.
- `gov + priv = 20`, and `gov ≈ 20 × gov_frac`. A government-built mill should say `gov_frac=1.00`.
- The construction queue now holds **Retooling: Steel Mills**, `gov` levels in the government queue
  and `priv` in the private one, each costing 100 construction.
- The mill carries the modifier **Retooling: Blister Steel Process to Bessemer Process**.

**7. Unpause for two weeks and read the mill's goods.** At p = 0 the lag holds Bessemer at Blister's
numbers: iron 60 × (1 − 0.33333) = **40** per level and steel 90 × (1 − 0.27778) = **65** per level,
coal **30** throughout. If the figures read 60 and 90, see the lag-modifier row in the null table.

**8. Let retooling build.** Each completed level writes, at once (from `on_building_built`):

```
PMR;rec=TICK;...;retool_built=1;retool_total=20;p=0.050
PMR;rec=TICK;...;retool_built=2;retool_total=20;p=0.100
...
```

p moves in steps of 1/(N × L) = 1/20. Iron per level is 40 + 20p and steel 65 + 25p, so at
`p=0.500` the mill reads 50 iron and 77.5 steel per level. The month-turn backstop writes the same
line again with the same p.

**9. When the twentieth level completes:**

```
PMR;rec=DONE;...;from=2;to=2;level=5;l_start=5;retool_built=20;retool_total=20;p=1.000
```

The lag modifier and the Retooling building are gone, and the mill reads 60 iron, 30 coal, 90
steel per level. Check that no **Retooling: Steel Mills** entry is left in either construction queue.

## Optional checks

- **Build a level mid-retool.** Queue one more Steel Mills level while retooling. When it lands,
  `level=6;l_start=5` and p jumps by (1 − p) ÷ 6 on top of the retool term, because the new level
  arrives already on Bessemer.
- **Switch back to Blister mid-retool.** Expect `rec=CANCEL;from=1;to=1;p=1.000`, the modifier and
  the Retooling building removed, and the mill back on Blister numbers at once.
- **Switch Blister → Open Hearth** (needs `open_hearth_process`): same shape as above with
  `to=3`, iron −0.55556 and steel −0.45833.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
