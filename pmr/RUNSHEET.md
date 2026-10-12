# PMR run sheet: retooling by level, one colour per recipe

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

**Start a new game, and leave `fastresearch` off.** `fastresearch` lets every country research
instantly. In the last autosave, 279 of 370 countries had the whole tree, compression ignition
included, by 1837. That is why Wallonia's sulfur mines went straight to Diesel Pump, and it fills
every country's construction queue with retooling.

## What changed in this build

- **The state tracks every level's recipe.** A Steel Mills of 8 levels might run 5 on Blister and 3
  on Bessemer. The recipe the building runs is the target. Every level on another recipe is still to
  retool, and each completed retool level moves one of them, oldest recipe first.
- **A newer recipe mid-retool keeps what is done.** If Open Hearth arrives while 3 of 8 levels are
  on Bessemer, those 3 stay on Bessemer and all 8 are now to retool towards Open Hearth. Retool
  levels already queued keep building and count towards the new target.
- **Retool buildings with anything queued are never removed.** Removing one left the queued
  construction with no building, which is the NULL_STATE entry you saw. When nothing is left to
  retool, PMR closes the building to new levels and removes it once its queue has emptied.
- **The recipe bar has one colour per recipe tier**, the same on every building: tier 1 red, 2
  yellow, 3 blue, 4 purple (5 green, only on wheat and rice farms). Oldest is on the left. Each
  segment is as wide as that recipe's share of the levels. The middle of the bar shows the share
  already on the target. Its tooltip lists every recipe's share and what each funder has queued.

Unchanged: who may fund retooling. Investors whose country owns part of the building fund the
private share, and the government funds its own share.

## Reading the log lines

`to` is the target recipe's tier. `levels` is the level count on each tier, oldest first, so
`5/3/0/0` means 5 levels on Blister and 3 on Bessemer. `p` is the target's share and `to_retool` is
the number of levels not on it. `gov_frac` and `gov_levels` give the government-owned share and the
levels it comes to. `share_gov` / `share_priv` split `to_retool` between government and investors.
`queued_gov` / `queued_priv` are retool levels queued but not yet built, and `room_gov` /
`room_priv` are how many more each side may queue.

## What each null means, decided before the run

| You see | It means | Not |
| --- | --- | --- |
| No `rec=LOADED` line | The mod is not in the playset, or `on_game_started` is not reaching appended on_actions. Check the playset first. | Anything about the design. |
| `rec=LOADED` but no `rec=INIT` lines | `pmr_state_tick` is not reaching buildings: `b:<building>` or `has_building` failed. Take **PMR test: recompute retooling now** and look again. | — |
| `error.log` names any `pmr_` script, `num_levels`, `levels_owned_by_country` or `investor_country` | Part of the script did not load or evaluate. Send me the lines. | A failure of the design. |
| The bar is grey or white although the tooltip shows two recipes above 0% | Vanilla's `color` override on its white progress bar does not tint in this panel. The instrument failed, not the model. | A failure of retooling. |
| The bar is one colour although the tooltip shows two recipes above 0% | The stacked segments are not drawn in order, or a `pmr_cum_` value did not read. Send a screenshot with the tooltip open. | — |
| A Retooling entry shows **NULL_STATE** in a queue again | A retool building was removed while levels were queued on it. Send me the `PMR;rec=` lines for that state around that date. | — |
| After **PMR test: grant Open Hearth**, Yorkshire's SWITCH line shows `levels=8/0/0/0` or `levels=0/0/8/0` | The level mix was reset instead of kept. | — |
| A retool level lands but the next line's `levels` and `to_retool` do not move | Completed levels are not being counted (`pmr_seen_`). | A failure of the investors. |
| Months pass with money in the pool, Yorkshire keeps `queued_priv=0;room_priv=8`, and no **Retooling: Steel Mills** appears in the Private queue | The ownership check refuses your own investors. Either `scope:investor_country` is not set where the game checks, or the `gov_levels` comparison failed. Hover **Retooling: Steel Mills** in Yorkshire's construction list and send me the tooltip. | A failure of the cap. |
| A **new** Retooling entry appears in your Private queue for a building your investors own none of | The ownership check is not applied. Send me the state and building. | — |
| Investors queue the first private level, then never a second, though `room_priv` is above 0 | The pool will not expand a building with no workforce. | — |
| More private retool levels are queued in Yorkshire than its `to_retool` | The private cap is not enforced: `level_after_queued_constructions` or `scope:num_levels` did not read as expected in `can_build_private`. | — |
| **Retooling (Government): Steel Mills** is not in the capital's construction list at all | Its `potential` failed, or the development lens does not list it. | — |
| It is listed but greyed out while the capital's line says `room_gov=5` | The government cap refused the first level. Send me the tooltip. | — |
| You can queue a sixth government level in the capital | The government cap is not enforced. | — |
| After a privatisation, the next line still shows the old `gov_frac` | `country_ownership_fraction` did not see the sale, or no tick has run yet. Take **PMR test: recompute retooling now** before calling it. | — |
| A completed retool level only shows at the month turn, not the day it lands | `on_building_expanded` or `on_building_built` does not run appended on_actions. The levels still catch up monthly. | A failure of retooling. |
| `error.log` says `Unknown modifier type: goods_..._mult` | The game did not accept `common/modifier_type_definitions/pmr_modifier_types.txt`, so the lag carries nothing. | — |
| The lag modifier shows on the building but the figures match plain Bessemer after two weeks | Building-scope `goods_*_mult` from a modifier is not read by the economy. Wait two weeks before calling it. | — |
| `rec=RESEARCH;...;best=2` but no `rec=SWITCH` follows, even after the month turns | `activate_production_method` in state scope did not switch the mill. | A failure of retooling. |
| The Buildings tab's Steel Mills row shows a recipe or automation button again | The shadowed `gui/production_methods.gui` stopped loading. | — |
| A field prints as text in brackets rather than a number | A log datafunction did not resolve on this build. The instrument failed, not the mod. | — |

## The run

**1. Install** (already copied to your mod folder). Start a **new** game with only this mod in the
playset.

**2. Start as Great Britain.** Before unpausing, expect `PMR;rec=LOADED` and one `rec=INIT` per
treated building. Yorkshire's line reads:

```
PMR;rec=INIT;...;state=Yorkshire;building=building_steel_mill;to=1;level=8;levels=8/0/0/0;p=1.000;to_retool=0;best=1
```

Every mill's bar is solid red with **100%** in the middle.

**3. Note the investment pool** on the **Construction** panel. If it reads £0, unpause for a few
weeks until it has money.

**4. Take `PMR test: grant Bessemer and a steel mill`.** It creates five government-owned levels in
the capital, then researches Bessemer. Without unpausing:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=2;level=8;levels=8/0/0/0;p=0.000;to_retool=8;gov_frac=0.00;gov_levels=0;share_gov=0;share_priv=8;queued_gov=0;queued_priv=0;room_gov=0;room_priv=8
PMR;rec=SWITCH;...;state=Home Counties;...;to=2;level=5;levels=5/0/0/0;p=0.000;to_retool=5;gov_frac=1.00;gov_levels=5;share_gov=5;share_priv=0;queued_gov=0;queued_priv=0;room_gov=5;room_priv=0
```

The mills read **Retooling to Bessemer Process** over an all-red bar showing **0%**.

**5. Queue the government's share.** In Home Counties, build **Retooling (Government): Steel Mills**
until it refuses. It should take exactly 5, in the Government queue, at 400 construction each.

**6. Unpause and watch the Private queue.** Expect **Retooling: Steel Mills in Yorkshire** under
Private, owned by a Financial District, never more than 8 in all.

**7. Check the lag after two weeks.** With every level still on Blister, each mill reads Blister's
figures (Yorkshire held 345 iron and 561 steel last time).

**8. Let some levels land.** Each one writes a `rec=TICK` the day it lands, with one more level moved
from the first figure to the second (`levels=7/1/0/0`, then `6/2/0/0`). On the bar, red shrinks
and yellow grows from the right.

**9. Your edge case: grant Open Hearth mid-retool.** While Yorkshire still has levels on Blister
(say `levels=5/3/0/0`) and some retooling is queued, take **PMR test: grant Open Hearth**. Expect:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=3;level=8;levels=5/3/0/0;p=0.000;to_retool=8;...
```

The bar shows red 5/8 and yellow 3/8, with no blue yet, under **Retooling to Open Hearth Process**.
The queued Retooling entries stay as they were: none turns into NULL_STATE. The Modifiers tab shows
two retooling modifiers, Blister to Open Hearth and Bessemer to Open Hearth. As levels land, red
goes first (`4/3/1/0`, `3/3/2/0`, and so on), then yellow, while blue grows from the right.

**10. When the last level moves:** `rec=DONE;...;levels=0/0/8/0;p=1.000;to_retool=0`, and the bar is
solid blue at 100%. If the DONE line shows `queued_priv` or `queued_gov` above 0, those levels still
build. The retool buildings stay until they land, then disappear.

## Optional checks

- **Privatise mid-retool.** The next line should show `gov_frac` falling, `room_gov` dropping, and
  `room_priv` taking the rest.
- **Build a level mid-retool.** When it lands, `level=` rises and the new level arrives on the target,
  so the target's figure in `levels` goes up by one.
- **Build a new Steel Mills elsewhere after Bessemer.** Expect `rec=ADOPT`, then `rec=INIT` with
  every level on the newest recipe and `p=1.000`.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
