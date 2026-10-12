# PMR run sheet: Blister → Bessemer, retooled by investors and the government

Every line PMR writes goes to `Documents\Paradox Interactive\Victoria 3\logs\debug.log` and starts
with `PMR;rec=`. Filter with:

```
findstr /C:"PMR;rec=" "%USERPROFILE%\Documents\Paradox Interactive\Victoria 3\logs\debug.log"
```

Also check `logs\error.log` for any line containing `pmr_` before reading anything else: a script
error there means the mechanism below never ran, and a missing log line is then not a result.

## How retooling is funded now

Nothing queues retooling for you any more. When research switches a building, PMR opens two
pseudo-buildings in its state and gives each a cap:

- **Retooling: Steel Mills** is built only by private investors, from the investment pool, for the
  privately owned share of the levels. While it has room its AI value is 1,000,000 against vanilla's
  usual 1,000, so the pool should pick it before anything else.
- **Retooling (Government): Steel Mills** is built only by the government, for the government-owned
  share. You queue it yourself from the state's Buildings tab or the development construction list.
  AI governments pick it the same way investors pick the private one.

Every tick re-reads who owns the mill. If the private sector buys government levels mid-retool, the
levels nobody has built or queued yet move to the private side, and the reverse for a
nationalisation. Levels already built or queued stay where they are.

The log lines carry: `gov_frac` (government-owned share of the mill), `built_gov` / `built_priv`
(completed retool levels), `with_queued_gov` / `with_queued_priv` (completed plus queued), and
`cap_gov` / `cap_priv` (the most each side may have, completed plus queued).

## What each null means, decided before the run

| You see | It means | Not |
| --- | --- | --- |
| No `rec=LOADED` line | The mod is not in the playset, or `on_game_started` is not reaching appended on_actions. Check the playset first. | Anything about the design. |
| `rec=LOADED` but no `rec=INIT` lines | `pmr_state_tick` is not reaching buildings: `b:<building>` or `has_building` failed. Take **PMR test: recompute retooling now** and look again. | — |
| `error.log` names `pmr_retool_room_`, `pmr_room_value_` or `num_levels` | The build caps did not load or evaluate, so the game decides who may build retooling without them. Send me the lines. | A failure of the investors. |
| Months pass with money in the investment pool, Yorkshire's line keeps `cap_priv=8;with_queued_priv=0`, and no **Retooling: Steel Mills** appears in the Private queue | The investment pool will not pick the retool building: either AI value does not steer it, or the cap check refuses investors. Hover **Retooling: Steel Mills** in Yorkshire's construction list and send me what the tooltip says it lacks. The fallback is PMR queuing the private levels itself, which worked last run. | A failure of the cap. |
| Investors queue the first private level, then never a second, though `cap_priv` is above `with_queued_priv` | The pool will not expand a building with no workforce. Vanilla skips expanding buildings it judges understaffed, and a retool building has no staff at all. | — |
| `with_queued_priv` passes `cap_priv`, or more than 8 private levels are ever queued in Yorkshire | The private cap is not enforced: `level_after_queued_constructions` or `scope:num_levels` did not read as expected in `can_build_private`. | — |
| **Retooling (Government): Steel Mills** is not in the capital's construction list at all | Its `potential` failed, or the development lens does not list it. The cap is untested; tell me. | — |
| It is listed but greyed out while the capital's line says `cap_gov=5;with_queued_gov=0` | The government cap refused the first level. Send me the tooltip. | — |
| You can queue a sixth government level in the capital | The government cap is not enforced. | — |
| After a privatisation, the next line still shows the old `gov_frac` and `cap_gov` | `country_ownership_fraction` did not see the sale, or ownership changed without a tick yet. Take **PMR test: recompute retooling now** before calling it. | — |
| A completed retool level only shows at the month turn, not the day it lands | `on_building_expanded` (later levels) or `on_building_built` (the first) does not run appended on_actions. p still catches up monthly. | A failure of retooling. |
| `error.log` says `Unknown modifier type: goods_input_iron_mult` (or any `goods_..._mult`) | The game did not accept PMR's definitions in `common/modifier_type_definitions/pmr_modifier_types.txt`, so the lag modifier carries nothing and the recipe switches at once. | — |
| Lag modifier shows on the building but the steel and iron figures match plain Bessemer after two weeks | Building-scope `goods_*_mult` from a timed modifier is not read by the economy. Ironroad measured up to 12 game days before an applied modifier shows in readbacks, so wait two weeks before calling it. | — |
| The setup decision writes `rec=RESEARCH;...;best=2` but no `rec=SWITCH` follows, even after the month turns | `activate_production_method` in state scope did not switch the mill. | A failure of retooling. |
| No `rec=RESEARCH` line after the setup decision | `can_activate_production_method` said no to Bessemer. Look at the INIT line's `best=`. | — |
| The Buildings tab's Steel Mills row shows a recipe or automation button again | The shadowed `gui/production_methods.gui` stopped loading. | — |
| The Steel Mills panel shows the Steelmaking Process or automation slot | The shadowed `gui/building_details_panel.gui` is not loading. | Anything about the economy. |
| The recipe bar reads 0% or stays all blue on a mill with a `rec=INIT` line | The panel cannot read the state variables PMR keeps for the mill. | A failure of retooling. |
| A field prints as text in brackets rather than a number | A log datafunction did not resolve on this build. The instrument failed, not the mod. | — |

## The run

**1. Install.** Copy `ProductionMethodRework` into `Documents\Paradox Interactive\Victoria 3\mod\`,
add it to a playset on its own, launch. Start a **new** game: retooling a save from an earlier
build carries that build's queued levels.

**2. Start as Great Britain.** Before unpausing, expect `PMR;rec=LOADED` and one `rec=INIT` per
treated building; every steel mill line says `from=1;to=1`.

**3. Note the investment pool** on the **Construction** panel. If it reads £0, unpause for a few
weeks until it has money: the private side of this test needs it.

**4. Take the decision `PMR test: grant Bessemer and a steel mill`.** If the capital has no Steel
Mills it creates five **government-owned** levels there, then researches Bessemer, which switches
every Steel Mills you own. Immediately, without unpausing:

```
PMR;rec=SWITCH;...;state=Yorkshire;building=building_steel_mill;from=1;to=2;level=8;...;retool_total=8;p=0.000;gov_frac=0.00;share_gov=0;share_priv=8;built_gov=0;built_priv=0;with_queued_gov=0;with_queued_priv=0;cap_gov=0;cap_priv=8
PMR;rec=SWITCH;...;state=Home Counties;building=building_steel_mill;from=1;to=2;level=5;...;retool_total=5;p=0.000;gov_frac=1.00;share_gov=5;share_priv=0;...;cap_gov=5;cap_priv=0
```

Both construction queues stay empty: nothing is queued for you.

**5. Queue the government's share yourself.** In Home Counties, open the construction list (or the
state's Buildings tab) and build **Retooling (Government): Steel Mills**. Add levels until it
refuses: it should take exactly 5, in the **Government** queue, each costing 400 construction. The
sixth should be greyed out. **Retooling: Steel Mills** (the private one) is listed too but greyed:
only investors may build it.

**6. Unpause and watch the Private queue.** Within a few weeks of the pool having money, expect
**Retooling: Steel Mills in Yorkshire** to appear under **Private**, owned by a Financial District,
one level per investment decision, and never more than 8 in all. Take **PMR test: recompute
retooling now** any time to read the counts:

```
PMR;rec=TICK;...;state=Yorkshire;...;built_priv=0;with_queued_priv=3;cap_priv=8
```

**7. Check the lag after two weeks**, as before: at p = 0 each mill reads Blister's 40 iron and 65
steel per level under Bessemer.

**8. Let retooling build.** Each completed level writes a `rec=TICK` the day it lands, from either
side. p = (levels built) ÷ (levels at the switch), so Yorkshire moves in eighths and Home Counties
in fifths. The recipe bar's tooltip shows each side: `Private owners: <built> built of <cap>` and
`Government: <built> built of <cap>`.

**9. When a mill's last level completes:** `rec=DONE;...;p=1.000`; both retool buildings are
gone from that state and neither queue holds a **Retooling** entry for it.

## Optional checks

- **Privatise mid-retool.** If the pool privatises the Home Counties mill (or you let it) before its
  government levels are all queued, the next tick should show `gov_frac` falling, `cap_gov`
  dropping to what is already built or queued, and `cap_priv` taking the rest. Investors then pick
  up the remainder.
- **Build a level mid-retool.** When it lands, `level=` rises and p jumps, because the new level
  arrives already on Bessemer.
- **Build a new Steel Mills elsewhere after Bessemer.** Expect `rec=ADOPT` then `rec=INIT;...;p=1.000`.

Send me the filtered `PMR;rec=` lines and the `error.log` lines containing `pmr_`, and say which row
of the null table matched if any did.
