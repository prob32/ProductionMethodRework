# PMR run sheet: electric automation as its own recipe, TREAT and PRICE probes, government levels, Owners column, retool crews

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

**Start a new game for this build**, including if you started one on d920da5. Recipes from the third
on change what they consume, and six building types gain a recipe. Leave `fastresearch` off for the
full run.

## What changed in this build

- **Electric automation is a recipe of its own.** Your Yorkshire tooling workshop on Steel Tools was
  using oil and electricity, because every recipe from the third on included Assembly Lines. Recipes
  from the third on now include the best automation that runs without electricity (Rotary Valve Engine
  for tools, so Steel Tools uses wood, steel and coal). Assembly Lines and Automatic Power Looms
  become one more recipe on top of the newest, e.g. "Machined Steel Tools + Assembly Lines". A
  building moves to it only when its owner has both technologies (Vulcanization and Conveyors for
  tools) and its state produces electricity. Textile mills, furniture, tooling, motor, arms and
  artillery each get one.
- **Buildings tab type rows count buildings abroad.** The tab lists buildings in other countries'
  states that you or your investors own levels in (your cotton plantations in the East India
  Company's states). The type row's bar summed only your own states, so a type with every building
  abroad stayed black. A player's bar now adds those buildings, whole, as their own bars show them,
  recounted monthly and the day after game start. The upgrade button still queues at home only.
- **Investment randomness** (your call in the investment thread): the investment pool's random roll
  on each building type now spans 1/11 to 11 instead of 1/21 to 21, for every building, through
  `common/defines/zz_pmr_ai.txt`. The 80% employment gate is unchanged.
- **Government upgrade button:** the government retools only its own levels that don't run the new
  recipe yet. Levels it builds new arrive on the new recipe and never count. (Your Sicily sulfur mine:
  2 new government levels on Atmospheric Engine Pump, 5 private levels on Picks and Shovels. The
  button offered 2; it now offers 0 and stays grey, and the private side gets all 5.)
- **Owners list:** a Production Method column between Owner and Levels Owned, with the icons of the
  recipes that owner's levels run. The government's row shows the government's levels; every private
  row shows the private owners' together (PMR tracks the two sides, not each owner). Hover for counts.
- **Recipe bar** in the building panel is 32 px tall, as tall as the cash reserves bar looks.
- **Buildings tab type row:** the bar was black until the first month passed, because at game start
  no country is a player's yet and the country totals were skipped. They are now computed for every
  country at game start. Each monthly recount writes `PMR;rec=CSUM`.
- **Retool crews:** each private retooling building has a fixed crew of 10 laborers, whatever its
  level, so it counts as fully employed and investors may add levels to it. Each empty one still
  takes one level as a new construction; the rest of the private room goes to the first one with a
  finished level. One whose crew hasn't reached 80% 90 days after its last level landed is removed
  once counted, as before.
- **Companies** list Retooling again (the first private retooling building of each type they list),
  so company panels show one Retooling icon per building type.
- `TICK` lines add `gov_lv=` (the government's levels per recipe), `slots=` (each private retooling
  building's levels including queued), `crew=` (-1 no finished level, 0 nobody hired, 1 some,
  2 at least 80%) and `unemp=` (the state's unemployment, at least 1, 2, 5, 10 or 20%; 0 below 1%).
- **Two log-only probes** for the next batch, plantation treatment and the market blend. They change
  nothing in game. See "Probes for the next batch" below.

## Checks

0. **Defines on load.** Before anything else, search `logs\error.log` for `zz_pmr_ai` and
   `RANDOM_FACTOR_MULT`. There should be no lines. A define that fails to merge is silent in game,
   and script can't read it back, so this is the only check that the 1/11 roll took effect.
1. **Government button.** In a new game, research a newer recipe for a building the government
   partly owns and let the government build a new level of it. The new level runs the new recipe;
   its `TICK` line shows `gov_lv=` with that level on the new recipe and `room_gov=` without it. If the
   government owns no old levels, the arrow is grey.
2. **Owners column.** Open a building with government and private owners. The Production Method
   column shows the government row's recipe icons and the private rows' icons; hover each for counts.
   Send a screenshot of the Owners list.
3. **Buildings tab bar.** From the second day, each PMR type row shows its recipe bar in the tier
   colours, not black, including Cotton Plantations, whose buildings are all abroad. Hover it: the
   level count includes the buildings abroad.
4. **Recipe bar height.** The bar lines up with the cash reserves bar. Screenshot.
5. **Stacking.** Let two years pass. On `TICK` lines with `room_priv` above 1, `slots=` should show
   2 or more on one building once its `crew=` reads 2.
6. **Electric recipes.** On day one, open the Yorkshire tooling workshop. Its Process box shows wood,
   steel and coal going in, and no oil or electricity. No PMR building whose recipe isn't one of the
   electric ones (or a vanilla recipe that uses electricity itself, such as Electric Arc Process)
   lists electricity. Screenshot the tooling workshop.

| You see | It means |
| --- | --- |
| The government arrow is lit on a building whose government levels all run the new recipe | The government's levels per recipe went wrong. Send me the `TICK` line (its `gov_lv=` and `gov_levels=`). |
| The Owners list overlaps or runs past the panel | The narrower copy of the row didn't take its new widths. Screenshot. |
| The type row bar is still black on day one and `PMR;rec=CSUM` lines appear from the first month | The totals exist but the bar can't read the country's variables. Screenshot plus any `error.log` line with `pmr_c_`. |
| Only types whose buildings are all abroad stay black after the second day, and a `CSUM` line was logged | The scan of states abroad finds nothing, so the ownership check doesn't match. Send the `error.log` lines with `levels_owned_by_country` or `pmr_c_sum`. |
| The type row bar is black and there is no `CSUM` line after a month | The monthly recount never runs. Send me the `error.log` lines with `pmr_`. |
| `crew=0` on a building with a finished level for 90 days | Nobody was hired: the game ignores a crew that doesn't scale with level, or no laborers would take the job. That building drops back to one level at a time. Open it from the state's building list and send its Workforce tab. |
| `crew=2`, `room_priv` above 1 and `slots=` never above 1 for two years | Employment was not what stopped investors stacking levels. Send me the lines. |
| `crew=2` and `slots=` 2 or more on one building | Stacking works. |
| An `error.log` line naming `zz_pmr_ai` or the define | The randomness change did not load, and the roll is still vanilla's 1/21 to 21. Send the line. |
| Steel Tools still lists oil or electricity | The game loaded the old build. Check the date of `common/production_methods/pmr_electric_production_methods.txt` in the mod folder, then send the Modifiers tab. |
| A building runs a "+ Assembly Lines" or "+ Automatic Power Looms" recipe whose owner lacks either technology, or in a state with no power plant | The gate failed. Send that building's `TICK` line. |
| `crew=2`, `room_priv` above 1, `slots=` stuck at 1 and `unemp=0` | The state is short of workers. The investment pool scores buildings x0.25 there once they employ anyone, so a strong rival may be winning the picks. Send the lines; compare with a state where `unemp` is 5 or more. |

## Probes for the next batch (log only)

Both run once a month in your own states and change nothing in game.

**TREAT**, one line per plantation:
`PMR;rec=TREAT;...;building=building_coffee_plantation;level=…;cur=…;vb=…;hb=…;w=…;wv=…;wh=…;ws=…;n=…;nv=…;nh=…;ns=…`

- `w` is the plantation's workforce. `wv`, `wh` and `ws` split it by acceptance: under 40 (Violent
  Hostility, Cultural Erasure: the violent share), 40 to 59 (Open Prejudice: the harsh share), 60 and
  over (standard). `n`, `nv`, `nh` and `ns` are the same counted by pop size, dependents included,
  as a fallback in case `w` reads 0.
- `cur` is the treatment it runs now: 2 Violent Treatment, 1 Exploitative Practices, 0 Standard
  Labor, 3 another method (tobacco's lectors or radio stations).
- `vb=1` means the owner's laws bar Violent Treatment; `hb=1` means they bar Exploitative Practices.

**PRICE**, two lines (hardwood and wood) per state with a logging camp:
`PMR;rec=PRICE;...;good=hardwood;base=40;f=…;p=…`

- `f` is the local price against the base price in steps of 5%: `f=35` means 35 to 40% above base,
  `f=-10` means 10 to 15% below. `p` reads the same with the threshold written in percent instead of
  as a fraction, because the game's docs don't say which it takes. One of the two will stay at 0.

7. **TREAT.** Pick a plantation with a `TREAT` line. Its `w` matches the employee total on its
   Workforce tab, and `wv + wh + ws = w`. Send a screenshot of the Workforce tab and the line. If one
   of your states has discriminated plantation workers, check their band against that state's Pops tab.
8. **PRICE.** Pick a state with a logging camp and open its market panel. The local price of hardwood
   and of wood should be base x (1 + f/100), within 5%. Send a screenshot and the two lines.

| You see | It means |
| --- | --- |
| No `TREAT` or `PRICE` lines at all after a month | The probe never ran. This is not a result about plantations or prices. Send the `error.log` lines with `pmr_probe` or `pmr_tr_`. |
| `w=0` on a staffed plantation and `n` above 0 | Workforce can't be summed this way. The build will count by pop size (`n`) instead. |
| `w=0` and `n=0` on a staffed plantation | No pop matched, so either the employment check or both counts read nothing. Send the `error.log` lines naming `workforce`, `total_size` or `pop_employment_building`. |
| `ws` equals `w` in a state whose Pops tab shows plantation workers under 60 acceptance | Acceptance read wrong. Send the Pops tab. |
| `wv + wh + ws` differs from `w` | The bands miss some pops. Send the line. |
| `f=0` and `p=0` for both goods in every state for a year | The price ladder never reads true. This does not mean prices sit at base. Send the `error.log` lines with `state_goods`. |
| `p` varies and `f` reads 75 or -75 almost everywhere | The threshold is in percent. The build will use the `p` ladder. |
| `f` varies and `p` stays 0 | The threshold is a fraction, as vanilla's railway rule suggests. The build will use the `f` ladder. |
| `sg=none` | The state has no market entry for that good. Harmless. |

## Checks from the previous build (b9c7304), still to confirm

1. **Panel row.** Open any PMR building. There is no goods icon; the recipe name starts at the left
   edge and the bar is about 290 px wide, ending where the employment bar starts.
2. **Workforce.** Open a building that is retooling (queue its government levels with the upgrade
   button and let one land). In the Workforce tab its jobs move towards the new recipe's as each level
   lands. Its Modifiers tab lists one `(… % of levels)` line per recipe, each with jobs and goods.
3. **Automation.** A mine whose newest recipe is Condensing Engine Pump: that recipe's share line in
   the Modifiers tab includes engines, coal and transportation inputs and fewer laborers. No mine,
   steel mill or factory shows an automation selector.
4. **Buildings tab.** Now check 3 of this build.
5. **Private retooling.** Let a year pass. For each building with `room_priv` above 0, read
   `home_investors` and `pool` on its `TICK` lines.

| You see | It means |
| --- | --- |
| A building's jobs never change as levels land, but its goods do | The share methods' employment is not read by the game. Send me the Workforce and Modifiers tabs. |
| A mine still shows an automation selector, or `error.log` names a production method group | The building file edit did not take. Send me the `error.log` lines. |
| The arrow on the type row never lights although a state's building panel arrow is lit | The country scripted GUI cannot see the state flags. Send me a screenshot of both. |
| A `TICK` line with `elec=0` shows `to=` an electric recipe that was not running before | The electricity lock failed. Send me the line. |
| `room_priv` above 0 for a year, `queued_priv=0`, `home_investors=0` | Your country's investors do not own enough of the building (at home they need more levels than the government) to fund its retooling. Ownership, not the pool. |
| The same, with `home_investors=1` and `pool=1000` or more | The pool is allowed and has money but never picks the retool buildings. Send me the lines: that points at how the pool scores them. |
| The same, with `pool=0` or `100` | The pool is too small to fund anything yet. Not a result. |

## Earlier checks, still to confirm

- **Goods counted once.** A building whose shares the tick had changed listed each switched recipe
  twice: Sicily's sulfur mine showed **Condensing Engine Pump (15% of levels)** and **Diesel Pump
  (10% of levels)** twice each in its Modifiers tab, and its inputs at about twice its blend.
  Buildings still on their starting share were right. A method change runs the tick it triggers
  inside the change, so one level landing ran about ten ticks nested in each other, and the log shows
  it (`SWITCH` written before the line of the tick that made the switch). Now only the outermost tick
  runs, and no share is activated while it already runs. Why the nesting doubled the goods is
  inferred: the outer tick activated again a share the inner one had already applied. The first try
  at this, the switching lock, stays: it does no harm and keeps the running share unlocked mid-change.

### The doubling check

1. Load your save (or start a new game) and open the Sicily sulfur mine, or any building with two
   recipes in its bar.
2. Open its **Modifiers** tab and hover each input. Each recipe appears **once**, as **Recipe (…
   of levels)**, and the figure is that line times the throughput. Sicily's tools, coal and oil
   should be about half what they were at the same employment.
3. Let a retool level land on that building, then hover again. Still once, and the log has one
   `rec=TICK` line for that building on that day, not ten.

| You see | It means |
| --- | --- |
| Right after loading, each recipe once and the figures halved, and still once after a level lands | Fixed. |
| Right after loading, each recipe once, but a recipe is listed twice again after a level lands | The guard did not stop it. Send me that building's `PMR;rec=` lines for that day and the Modifiers tab. |
| A landing day still writes many identical `rec=TICK` lines for one building | The guard flag is not holding, so ticks still nest. Send me a few of the lines. |
| Right after loading, a recipe is still listed twice | The doubling is saved with the building, not made at runtime, so loading does not clear it. A new game is the test of this build; send me the tooltip either way. |
| A tier's `active` reads `-1`, or `active` and `blend` differ on two lines in a row for one building | The switching lock left a share group without a method. Send me the lines. |

### Earlier in this build

- **Old recipes' goods are now in the building's own production figures.** Each recipe has a hidden
  share method carrying its goods (and pollution) times its share of the building's levels, in 1%
  steps (5% before this build). An iron mine with 15 levels on Atmospheric and 5 on Condensing lists **Atmospheric Engine
  Pump (75% of levels)** and **Condensing Engine Pump (25% of levels)** in its input and output
  tooltips, coal included, scaled by employment and throughput exactly like a vanilla recipe. Its
  profit, and the investment AI's view of it, use those figures. The **Not yet retooled** and lag
  modifiers are gone.
- **Up to four private retool levels per building at a time.** Each building type has four private
  retool slots, each holding one level, so a state can show up to four **Retooling: Iron Mines**
  entries in the Private queue at once, plus the government's.
- **Companies no longer list Retooling.** Company panels show only their own building types again.
  A building a company owns still retools through investors from the company's country.
- Unchanged: research switches the recipe, the level mix, the bar colours, who may fund retooling,
  and the government cap.

## Reading the log lines

`to` is the target recipe's tier. `levels` is the level count on each tier, oldest first, so
`5/3/0/0` means 5 levels on Blister and 3 on Bessemer. `p` is the target's share and `to_retool` is
the number of levels not on it.

`blend` is each tier's share in percent as the tick set it (`75/25/0/0`), and `active` is the same
figure for each tier whose share method the game reports running, `-1` where it does not. They match
when the blend has been applied, which with the guard should be on every line.

`gov_frac` and `gov_levels` give the government-owned share and the levels it comes to.
`share_gov` / `share_priv` split `to_retool` between government and investors. `queued_gov` /
`queued_priv` are retool levels queued but not yet built, and `room_gov` / `room_priv` are how many
more each side may queue.

While a building retools, every method change on it writes another `rec=TICK` line, so a level
landing usually brings two or three lines for that building on the same day.

## What each null means, decided before the run

| You see | It means | Not |
| --- | --- | --- |
| No `rec=LOADED` line | The mod is not in the playset, or `on_game_started` is not reaching appended on_actions. Check the playset first. | Anything about the design. |
| `rec=LOADED` but no `rec=INIT` lines | `pmr_state_tick` is not reaching buildings. Take **PMR test: recompute retooling now** and look again. | — |
| `error.log` names any `pmr_` script, method or group | Part of the script did not load. Send me the lines. | A failure of the design. |
| A mill's input and output tooltips show no **(… of levels)** line at all, and its figures are zero | The share methods are not applying: the defaults did not take on load. Send me a screenshot of the tooltip and the mill's `rec=INIT` line. | A failure of retooling. |
| `active` stays behind `blend` across two lines for the same building, and the tooltip shows the old percentages | The share method was refused although the switching lock was active, and the lock's own method change did not bring a second tick. Take **PMR test: recompute retooling now**; if `active` then catches up, the blend works one tick late. | A failure of the level mix. |
| `active` shows `-1` for a tier | None of that tier's share methods is running. The game dropped the method when its lock changed. Send me the line. | — |
| An input tooltip lists the same **Recipe (… of levels)** line twice, or a building's inputs are about twice its blend | A share's goods are counted twice. See the doubling check above. | A failure of the level mix. |
| The same building writes dozens of `rec=TICK` lines on one day | The method changes are retriggering each other. Send me a few of the lines. | — |
| The figures move but the tooltip's percentages and `blend` disagree | The rounding or the tier order is off. Send me the line and the tooltip. | — |
| The bar is grey, white or one colour although the tooltip shows two recipes above 0% | The bar failed, not the model. Send a screenshot with the tooltip open. | A failure of retooling. |
| A Retooling entry shows **NULL_STATE** in a queue | A retool slot was removed while a level was queued on it. Send me that state's `PMR;rec=` lines around that date. | — |
| Months pass with money in the pool and a building with `room_priv` of 2 or more never has more than one **Retooling:** entry queued at a time | The pool picks one slot per building at a time anyway. Still better than before: each lands and the next opens. Send me the tooltip of an open slot that is not being built. | A failure of the cap. |
| More than four **Retooling: Steel Mills** in Yorkshire in the Private queue at once, or more than `to_retool` | The slot check (`level_after_queued_constructions < 1` in `can_build_private`) is not holding. | — |
| Months pass with money in the pool, Yorkshire keeps `queued_priv=0` with `room_priv` above 0, and no **Retooling: Steel Mills** appears | The ownership check refuses your own investors. Hover **Retooling: Steel Mills** in Yorkshire's construction list and send me the tooltip. | A failure of the cap. |
| A **Retooling:** entry appears in your Private queue for a building your investors own none of | The ownership check is not applied. Send me the state and building. | — |
| A retool level lands but the next line's `levels` and `to_retool` do not move | Completed levels are not being counted (`pmr_seen_`). | A failure of the investors. |
| After **PMR test: grant Open Hearth**, Yorkshire's SWITCH line shows `levels=8/0/0/0` or `levels=0/0/8/0` | The level mix was reset instead of kept. | — |
| **Retooling (Government): Steel Mills** is not in the capital's construction list, or is listed but greyed out while the capital's line says `room_gov=5` | Its `potential` or the government cap failed. Send me the tooltip. | — |
| You can queue a sixth government level in the capital | The government cap is not enforced. | — |
| `rec=RESEARCH;...;best=2` but no `rec=SWITCH` follows, even after the month turns | `activate_production_method` in state scope did not switch the mill. | A failure of retooling. |
| A company panel still shows **Retooling** icons | The old company files are still in the mod folder. Check `mod\ProductionMethodRework\common` has no `company_types` folder. | — |
| A field prints as text in brackets rather than a number | A log datafunction did not resolve on this build. The instrument failed, not the mod. | — |

## The run

**1. Install** (already copied to your mod folder). Start a **new** game with only this mod in the
playset.

**2. Start as Great Britain.** Before unpausing, expect `PMR;rec=LOADED` and one `rec=INIT` per
treated building. Yorkshire's steel mill line reads:

```
PMR;rec=INIT;...;state=Yorkshire;building=building_steel_mill;to=1;level=8;levels=8/0/0/0;p=1.000;to_retool=0;best=1;blend=...
```

The `blend` and `active` fields on INIT are written before the first blend, so ignore them there.
Every mill's bar is solid red with **100%** in the middle.

**3. Check the starting figures.** Open Yorkshire's Steel Mills and hover its iron input and steel
output. Each lists **Blister Steel Process (100% of levels)** and no other recipe line, and the
figures match vanilla Blister (Yorkshire held 345 iron and 561 steel last time). Also note the
investment pool on the **Construction** panel; if it reads £0, unpause for a few weeks.

**4. Take `PMR test: grant Bessemer and a steel mill`.** It creates five government-owned levels in
the capital, then researches Bessemer. Without unpausing:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=2;level=8;levels=8/0/0/0;p=0.000;to_retool=8;blend=100/0/0/0;active=100/0/0/0;...;room_gov=0;room_priv=8
PMR;rec=SWITCH;...;state=Home Counties;...;to=2;level=5;levels=5/0/0/0;p=0.000;to_retool=5;blend=100/0/0/0;active=100/0/0/0;...;room_gov=5;room_priv=0
```

The mills read **Retooling to Bessemer Process** over an all-red bar showing **0%**, and the
tooltips still show Blister at 100%: nothing has been retooled yet.

**5. Queue the government's share.** In Home Counties, build **Retooling (Government): Steel Mills**
until it refuses. It should take exactly 5, in the Government queue, at 400 construction each.

**6. Unpause and watch the Private queue.** Expect up to four **Retooling: Steel Mills in
Yorkshire** entries under Private at once, owned by a Financial District, never more than 8 in all.

**7. Let some levels land.** Each one writes a `rec=TICK` the day it lands, with one more level
moved from the first figure to the second, and the blend following:

```
PMR;rec=TICK;...;state=Yorkshire;...;levels=6/2/0/0;...;blend=75/25/0/0;active=75/25/0/0;...
PMR;rec=TICK;...;state=Yorkshire;...;levels=4/4/0/0;...;blend=50/50/0/0;active=50/50/0/0;...
```

Shares round to the nearest 1% (7 of 8 levels shows as 88%).
`active` may trail `blend` on the first line of a day and match on the next. The mill's tooltips now
list **Blister Steel Process (75% of levels)** and **Bessemer Process (25% of levels)**, and its iron,
coal and steel figures sit between the two recipes'. On the bar, red shrinks and yellow grows from
the right. When a slot's level lands and nothing else is queued on it, that **Retooling:** building
leaves Yorkshire's building list and the slot opens for the next level.

**8. Your edge case: grant Open Hearth mid-retool.** While Yorkshire still has levels on Blister
(say `levels=4/4/0/0`) and some retooling is queued, take **PMR test: grant Open Hearth**. Expect:

```
PMR;rec=SWITCH;...;state=Yorkshire;...;to=3;level=8;levels=4/4/0/0;p=0.000;to_retool=8;blend=50/50/0/0;...
```

The bar shows red and yellow at half each, with no blue yet, under **Retooling to Open Hearth Process**,
and the tooltips list Blister and Bessemer and no Open Hearth. Queued Retooling entries stay as they
were: none turns into NULL_STATE. As levels land, red goes first (`3/4/1/0`, `2/4/2/0`, and so
on), then yellow, while blue grows from the right.

**9. When the last level moves:** `rec=DONE;...;levels=0/0/8/0;p=1.000;to_retool=0;blend=0/0/100/0`,
the bar is solid blue at 100%, and the tooltips list only **Open Hearth Process (100% of levels)**.
If the DONE line shows `queued_priv` or `queued_gov` above 0, those levels still build. The retool
buildings stay until they land, then disappear.

## Optional checks

- **Your iron mine case.** After Diesel Pump on a mine with Atmospheric levels left, the coal input
  lists **Atmospheric Engine Pump (… of levels)** for as long as any level runs it.
- **Privatise mid-retool.** The next line should show `gov_frac` falling, `room_gov` dropping, and
  `room_priv` taking the rest.
- **Build a level mid-retool.** When it lands, `level=` rises and the new level arrives on the target,
  so the target's figure in `levels` goes up by one.
- **Build a new Steel Mills elsewhere after Bessemer.** Expect `rec=ADOPT`, then `rec=INIT` with
  every level on the newest recipe and `p=1.000`.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
