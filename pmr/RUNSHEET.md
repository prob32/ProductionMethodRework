# PMR run sheet: retooling by level, one colour per recipe

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

## First, on your current save

Load the exit autosave from your last session (Great Britain, September 1838) and take **PMR test: recompute
retooling now** before unpausing.

1. **Coal.** Open Yorkshire's Iron Mines. The Modifiers tab lists **Not yet retooled: Atmospheric
   Engine Pump**, and its inputs show coal again: about 10 per Atmospheric level times the mine's
   employment, so about 50 at full employment, beside the Tools and Oil you saw.
2. **Second levels.** Unpause for three months. Expect new **Retooling:** entries in the Private
   queue for buildings that already had a level land, such as Yorkshire's Iron Mines or Wales's Coal
   Mines, and their `rec=TICK` lines showing `queued_priv=1` again.

**Start a new game, and leave `fastresearch` off.** `fastresearch` lets every country research
instantly. In the last autosave, 279 of 370 countries had the whole tree, compression ignition
included, by 1837. That is why Wallonia's sulfur mines went straight to Diesel Pump, and it fills
every country's construction queue with retooling.

## What changed in this build

- **Levels still on an old recipe keep the goods the new recipe lacks.** Your Yorkshire iron mine,
  5 levels on Atmospheric and 1 on Diesel, lost its coal because the old recipe's figures were
  scaled from Diesel's, and Diesel has no coal. Those goods now come from a second modifier per old
  recipe, **Not yet retooled: Atmospheric Engine Pump**, which adds that recipe's per-level amount
  (10 coal) for each level still on it, times the mine's occupancy.
- **Investors can now queue more than one retool level per building.** In your last log every
  private retool level investors queued was the first for its building. Once one had landed,
  none got a second: Yorkshire's steel mill sat at `room_priv=6` for twenty months. The game's
  investment AI does not expand a building with under 80% employment, and a retool building employs
  nobody. PMR now removes a retool building as soon as its levels are counted and nothing is queued
  on it, so the next level is a new construction again. One level per building is under
  construction at a time.
- **Companies can retool the building types they own.** Each company that lists a building type
  now also lists its **Retooling:** building, so the investment pool can make the company the owner
  of the retooling, as it does for new levels of that type, most often in the company's
  headquarters state. Side effect: company panels show the Retooling icons beside their building
  types.
- Unchanged: one colour per recipe tier, the level mix, who may fund retooling, and the queue rules.

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
| After the recompute, Yorkshire's Iron Mines show no **Not yet retooled** modifier | The modifier was not applied: the `occupancy` trigger read 0 or the apply step did not run. Send me Yorkshire's `rec=TICK` line and the error.log `pmr_` lines. | A failure of the level mix. |
| The **Not yet retooled** modifier is there but the mine's inputs still show no coal after two weeks | The economy ignores a flat `goods_input_coal_add` from a building modifier. Wait two weeks before calling it. | A failure of the level mix. |
| Coal is back but well below 10 per Atmospheric level although the mine is fully staffed | The game applies throughput bonuses to the recipe's goods and not to the modifier's. Send me the figure. | — |
| Months pass with money in the pool and no building that already had a level land ever gets another queued, though `room_priv` is above 0 | Removing and re-creating the retool building does not bring the pool back. The 80% employment rule is not the cause. Hover the **Retooling:** building in that state's construction list and send me the tooltip. | A failure of the cap. |
| A retool building disappears from the state while a level was still queued on it | The new removal step ran with something queued. Send me that state's `PMR;rec=` lines around that date. | — |
| `error.log` names `company_types` or a `building_pmr_retool_` type in a company | A company file did not load with the added line. Send me the lines. | — |
| A year in, no **Retooling:** entry in your Private queue has ever shown a company as owner, though companies own treated buildings | Company ownership of retooling is not applied. The chance scales with how much of the pool comes from companies, so a few entries are not enough to call it. | — |
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
and yellow grows from the right. When a level lands and nothing else is queued, the **Retooling:**
building leaves Yorkshire's building list, and investors queue the next level as a new one.

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
