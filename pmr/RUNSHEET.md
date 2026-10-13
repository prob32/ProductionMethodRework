# PMR run sheet: 1% blend, recipe bar, government upgrade button

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

**Your current save works with this build** if it was started on the blended build (the one with
four retool slots). Its share methods now mean 1% steps instead of 5%, so right after loading take
**PMR test: recompute retooling now** (or wait for the month to turn) before reading any figures.
Saves from before the blended build still need a new game: they carry modifiers and retool
buildings it no longer defines. Leave `fastresearch` off
for the full run: it lets every country research instantly and fills every construction queue with
retooling. For a quick look at the blend
alone, step 4 below grants one technology to you only.

## What changed in this build

- **1% steps.** Each recipe's share is now blended to the nearest 1%, so an 11-level building at
  6/0/4/1 reads 55%, 36% and 9% in its tooltips, the same as the bar.
- **The recipe bar** is now built like the Owners bar: one slice per recipe, oldest on the left, in
  muted colours (bronze, ochre, steel blue, plum, slate; no red or green), with the recipe's icon
  centred on any slice over 25%. While retooling, the line above it reads **9% on Diesel Pump**.
- **Government upgrade button**, the gold arrow beside the recipe name, against the employment bar.
  It queues every government retooling level the building still needs. It is greyed out when the
  government owns none of the levels still to retool, has queued them all, or the state is not yours.
- **Buildings tab:** each row shows the recipe bar beside the gold labour icon, and the upgrade
  button left of nationalize. The tab is 35 px wider to make room.

### The new UI, after the doubling check below

1. Open a building that is retooling and has government-owned levels (a mine you built with the
   government, or Home Counties after `PMR test: grant Bessemer and a steel mill`). The arrow
   button is lit. Hover it: it says how many levels it will queue.
2. Click it. The Government queue gains exactly that many **Retooling (Government): …** entries, the
   button greys out, and the log has one line:
   ```
   PMR;rec=GOV_QUEUE;...;room_gov=5;...;queueing=5
   ```
   followed by a `rec=TICK` line with `queued_gov=5;room_gov=0`.
3. Open the **Buildings** tab: the same button sits left of nationalize on that building's row, greyed
   out now, and the recipe bar sits beside the gold icon.

| You see | It means |
| --- | --- |
| The button never lights, even with `room_gov` above 0 in the log | The scripted GUI's `is_valid` is not reading the state's flag. Hover it and send me the tooltip. |
| You click a lit button and nothing is queued, and no `rec=GOV_QUEUE` line | The scripted GUI did not run. Send me `error.log` lines containing `sgui` or `pmr_`. |
| `rec=GOV_QUEUE` is logged but the queue gains nothing | `start_building_construction` refused the retool building. Send me the line and the tooltip of **Retooling (Government): …** in that state's construction list. |
| The bar is empty, or one slice fills it although the tooltip lists two recipes above 0% | The slice widths (`layoutstretchfactor_horizontal`) did not read the shares. Send me a screenshot with the tooltip open. |
| The Buildings tab's rows run off the right edge or the last buttons are cut | The 35 px widening did not fit your screen. Send me a screenshot. |

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
