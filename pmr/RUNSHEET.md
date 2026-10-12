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
| `rec=SWITCH` with `queued=1` while `retool_total=5` | Repeated `start_building_construction` calls collapse into one queue entry. The fix is to queue one level at a time as each completes; tell me and I'll switch it. | — |
| **Retooling: Steel Mills** sits in the government queue while the SWITCH line says `gov=0` | The privately funded effect still lands in the government queue even with the retool building marked `ownership_type = self` and its group `is_government_funded = no`. The private queue then cannot be reached this way; tell me. | A misread of ownership: `gov_frac` is what the mill's owners say. |
| `gov_frac=0.00` on a government-owned mill | `country_ownership_fraction` does not read government ownership; everything goes to the private queue. | — |
| `error.log` says `Unknown modifier type: goods_input_iron_mult` (or any `goods_..._mult`) | The game did not accept PMR's definitions in `common/modifier_type_definitions/pmr_modifier_types.txt`, so the lag modifier carries nothing and the recipe switches at once. | — |
| Lag modifier shows on the building but the steel and iron figures match plain Bessemer after two weeks | Building-scope `goods_*_mult` from a timed modifier is not read by the economy. This kills design point 3 as written. Ironroad measured up to 12 game days before an applied modifier shows in readbacks, so wait two weeks before calling it. | — |
| The setup decision writes `rec=RESEARCH;...;best=2` but no `rec=SWITCH` follows, even after the month turns | `activate_production_method` in state scope did not switch the mill. Recipes cannot change without the selector, so tell me and I'll move the switch to another effect. | A failure of retooling. |
| Researching a recipe normally (or through the console) gives no `rec=RESEARCH` until the month turns | `on_acquired_technology` did not fire for that kind of research. The monthly tick still switches the building; take **PMR test: recompute retooling now** to see it at once. | A failure of the switch. |
| No `rec=RESEARCH` line after the setup decision | `can_activate_production_method` said no to Bessemer in the capital. Look at the INIT line's `best=`: if it reads 1 after the research, this trigger is the problem. | — |
| The Buildings tab's Steel Mills row still shows a Steelmaking Process or automation button | The shadowed `gui/building_browser_panel.gui` is not loading, or its building-type check failed. | — |
| The Steel Mills panel still shows the Steelmaking Process or automation slot | The shadowed `gui/building_details_panel.gui` is not loading, or its building-type check failed. The selectors are hidden by building type, not by any script state. | Anything about the economy. |
| The recipe bar reads 0% or stays all blue on a mill with a `rec=INIT` line | The panel cannot read the state variables (`pmr_bar_old_steel_mill` and the like) PMR keeps for the mill. | A failure of retooling. |
| The recipe bar's name is blank or shows `pmr_new_recipe` | The building custom localization did not resolve. The bar's numbers still stand. | — |
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

**3. Open any steel mill's panel.** The production method row shows one slot only: a gold steel
beam, with no dropdown. Its tooltip is **Fixed Workforce**: per level the building employs 500
shopkeepers, 3,500 laborers, 750 machinists and 250 engineers. The recipe and automation slots are
gone.

To its right, between that slot and the employment and cash-reserve bars, is the recipe bar: the
top line reads **Blister Steel Process**, and under it a full gold bar reads **100%**.

**4. Note the capital mill's numbers on Blister** before anything else, at full staffing: per level
40 iron and 30 coal in, 65 steel out. If the capital has no Steel Mills, skip this; the decision
creates one.

**5. Take the decision `PMR test: grant Bessemer and a steel mill`.** If the capital has no Steel
Mills it creates five levels there on Blister, then it researches Bessemer. There is no recipe
selector any more: research is what switches the mill. Immediately, without unpausing:

```
PMR;rec=TEST;arm=SETUP;date=...;country=Great Britain;state=Home Counties
PMR;rec=RESEARCH;...;building=building_steel_mill;from=1;to=1;...;best=2
PMR;rec=SWITCH;...;building=building_steel_mill;from=1;to=2;level=5;l_start=5;retool_built=0;retool_total=5;p=0.000;gov_frac=<f>;gov=<g>;priv=<5-g>;queued=5
PMR;rec=TICK;...;from=1;to=2;level=5;l_start=5;retool_built=0;retool_total=5;p=0.000;queued=5
```

If the decision created the mill, an `INIT` line with `level=5;best=1` comes before the
`RESEARCH` line. If `SWITCH` only appears when the month turns, the activation applied late; that
is fine.

**6. Read the capital mill's panel.** The recipe bar's top line now reads **Retooling to Bessemer
Process**; the bar is all gold with **100%** at the left and **0%** at the right. Its tooltip names
both recipes and reads `Retooling levels built: 0 of 5`.

- `retool_total=5` is one retooling level per building level.
- `gov + priv = 5`, and `gov ≈ 5 × gov_frac`. A government-built mill should say `gov_frac=1.00`; one owned by Financial Districts or other private owners should say `gov_frac=0.00` and queue every level privately.
- The construction queue now holds **Retooling: Steel Mills**, `gov` levels in the government queue
  and `priv` in the private one, each costing 400 construction (half a Steel Mills level).
- The mill carries the modifier **Retooling: Blister Steel Process to Bessemer Process**.

**7. Unpause for two weeks and read the mill's goods.** While paused, the panel shows plain Bessemer figures the moment the recipe changes: the game applies the recipe at once but only recomputes modifiers on its daily tick. Check the **Modifiers** tab for **Retooling: Blister Steel Process to Bessemer Process** before unpausing. At p = 0 the lag holds Bessemer at Blister's
numbers: iron 60 × (1 − 0.33333) = **40** per level and steel 90 × (1 − 0.27778) = **65** per level,
coal **30** throughout. If the figures read 60 and 90, see the lag-modifier row in the null table.

**8. Let retooling build.** Each completed level writes, at once (from `on_building_built`):

```
PMR;rec=TICK;...;retool_built=1;retool_total=5;p=0.200
PMR;rec=TICK;...;retool_built=2;retool_total=5;p=0.400
...
```

p moves in steps of 1/L = 1/5. Iron per level is 40 + 20p and steel 65 + 25p, so at
`p=0.600` the mill reads 52 iron and 80 steel per level. The month-turn backstop writes the same
line again with the same p. The recipe bar follows: blue grows from the right by 20% a level, and
the two labels read 1 − p and p.

**9. When the fifth level completes:**

```
PMR;rec=DONE;...;from=2;to=2;level=5;l_start=5;retool_built=5;retool_total=5;p=1.000
```

The lag modifier and the Retooling building are gone, and the mill reads 60 iron, 30 coal, 90
steel per level. Check that no **Retooling: Steel Mills** entry is left in either construction queue.
The recipe bar is full gold again and reads **Bessemer Process**, **100%**.

## Optional checks

- **Build a level mid-retool.** Queue one more Steel Mills level while retooling. When it lands,
  `level=6;l_start=5` and p jumps by (1 − p) ÷ 6 on top of the retool term, because the new level
  arrives already on Bessemer.
- **Build a new Steel Mills elsewhere after Bessemer.** When its first level lands, expect
  `rec=ADOPT;...;from=2;to=2` and then `rec=INIT;...;p=1.000`: a new building starts on the newest
  recipe its owner has, with no retooling. Its recipe bar reads **Bessemer Process**, **100%**.
- **Research Open Hearth** (`open_hearth_process`) on a mill that runs Bessemer: same shape as step 5
  with `best=3;to=3`, iron −0.55556 and steel −0.45833.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
