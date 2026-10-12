# Production Method Rework (PMR)

A script-only Victoria 3 mod. Labour is fixed per building, recipes swap by technology as ordinary
production methods, and a recipe switch takes effect gradually as retooling construction completes.

- `ProductionMethodRework/` is the mod folder. Copy it into
  `Documents\Paradox Interactive\Victoria 3\mod\` and enable it in a playset.
- `RUNSHEET.md` is the test handover: what to do in game and the exact
  `debug.log` lines to look for, including what each null means.
- `tools/pmr/generate.py` writes the whole mod from the installed game's own script. Re-run it after
  every beta update: `python tools/pmr/generate.py --game "G:/SteamLibrary/steamapps/common/Victoria 3/game"`.
- `GENERATION_REPORT.json`, written into the generated mod folder, lists every building treated, every building
  skipped and why, and every lag entry the design cannot express.

The mod output is not committed. It is generated locally from the installed game's script and copied
into the mod folder; only the generator, the design notes and the run sheet live in the repo. Target:
the 1.14.x open beta, `supported_version = 1.14.*`.

## The design, as built

| Design point | Where it lives |
| --- | --- |
| 1. Labour is fixed | Each treated building gets `pmg_pmr_labour_<b>` with one method, `pm_pmr_labour_<b>`, holding the default recipe's `level_scaled` employment. The recipe methods lose their `building_employment_*` lines. Steel: shopkeepers 500, laborers 3500, machinists 750, engineers 250, from Blister. |
| 2. Recipes are ordinary methods | The vanilla recipe methods, unchanged apart from employment: `goods_input_<g>_add` / `goods_output_<g>_add` in `workforce_scaled`. Vanilla files are shadowed whole under their own names, so every other byte is the game's. |
| 3. Gradual switch | The state keeps how many of the building's levels run each recipe (`pmr_lv_<i>_<b>`, i = the recipe's place in vanilla's group, oldest first). The recipe the building runs is the target; every level on another recipe is still to retool. `common/static_modifiers/pmr_lag_modifiers.txt` has one modifier per ordered recipe pair, values old/new − 1. For each recipe i still running on some levels, the building carries the i → target modifier with `multiplier` = i's share of the levels, so its goods are the level-weighted mix of its recipes. Steel Blister → Bessemer is `goods_input_iron_mult = -0.33333`, `goods_output_steel_mult = -0.27778`, no coal entry. |
| 4. p is driven by construction | Two pseudo-buildings per building type, each costing 50% of the building's construction cost ÷ N per level, with N = 1 (steel: 800 × 0.5 = 400). `building_pmr_retool_<b>` is built only by private investors, for the privately owned share of the levels still to retool; `building_pmr_retool_gov_<b>` only by the government, for its share. Nothing queues them: the investment pool picks the private one (AI value 1,000,000 while it has room) and the player, or an AI government, builds the government one. `can_build_private` / `can_build_government` cap each at its share, the way vanilla caps trade centers under the canton system. `can_build_private` also requires the investing country's investors to own part of the building (`levels_owned_by_country`; for the state's own country, more than the government's levels), so an investment agreement alone does not let a foreign pool retool it. Every tick re-splits the levels nobody has queued by current ownership, so a privatisation mid-retool hands the rest to investors. A retool building is never removed while it has levels queued: removing it leaves a construction with no building, shown as NULL_STATE in the queue. It is closed instead and removed once its queue empties. |
| 5. Each completed retool level moves one building level | `pmr_progress_<b>`: retool levels completed since the last tick (both buildings' `level` less `pmr_seen_<b>`, ÷ N) move that many levels onto the target, oldest recipe first. New building levels arrive on the target; lost levels go from the oldest recipe first. p is the target's share. When every level is on the target the lag goes, and the retool buildings once nothing is queued on them. |

| The building panel | A shadowed `gui/building_details_panel.gui` (vanilla's, with two patches the generator asserts). On a PMR building the production method row shows only the fixed labour slot, drawn as the building's main output good in gold (`tools/pmr/icons.py`, written to `gfx/.../production_method_icons/pmr_labour_<b>.dds`). Beside it a recipe bar, sized to sit between that slot and the employment and cash-reserve bars: one segment per recipe, oldest on the left, as wide as that recipe's share of the levels and coloured by its tier, the same on every building (`TIER_COLORS`: 1 red, 2 yellow, 3 blue, 4 purple, 5 green). The segments are vanilla white progress bars tinted per tier, filled to the running total of the shares (`pmr_cum_<i>_<b>`) and stacked newest first. Its tooltip lists every recipe's share; the title reads the building custom localization `pmr_new_recipe`. |
| Recipes switch on research | With the selector gone, each tick finds the newest recipe the building can run (the last in the vanilla group that `can_activate_production_method` allows) and, when that rises, activates it, which starts retooling like any switch. A newly constructed building starts on the newest recipe at no cost. |

p is recomputed on these hooks, all appended to vanilla on_actions the documented way:
`on_production_method_changed` (the switch is seen at once), `on_acquired_technology` (research
switches at once), `on_building_built` and `on_building_expanded` (a building's first level and each
later one; together every completed retool level moves p at once), and `on_monthly_pulse_state`
(backstop). A save that predates the mod
adopts each building's current recipe with no lag on its first tick.

## Scope

Treated: every building in industry, agriculture, mining, plantations and the
misc-resource file (logging, fishing, whaling, oil, rubber) whose first production method group
holds two or more recipes. Skipped: synthetics plant, electrics industry and gold fields (one recipe
each), and the government, military, urban, infrastructure, monument, canal, subsistence, company
and construction-sector buildings, whose first group is not a goods recipe or whose retooling would
be paid for by itself.

## Goods modifier types

1.14.5 only accepts a `goods_input_<good>_mult` or `goods_output_<good>_mult` modifier once
`modifier_type_definitions` defines it; vanilla defines a handful. The generator writes the rest the
lag modifiers use into `common/modifier_type_definitions/pmr_modifier_types.txt`, in vanilla's
format, and lists them in `GENERATION_REPORT.json`. Without them the lag modifier is empty and a
recipe switch takes effect at once.

## Where PMR keeps its numbers

Buildings cannot hold script variables on 1.14.5 (`This scope doesn't support variables. Scope:
Building`), so every number PMR keeps for a building lives on its state, named by building type:
`pmr_p_steel_mill` on a state is that state's steel mill's p. A state has at most one building of
each type. The tick runs in state scope and touches the building through `b:<type>` only to add
or remove the lag modifier and to read its ownership.

## Choices made where the design was silent

- **Only the recipe group is stripped of labour.** Automation and other secondary groups keep their
  vanilla employment changes (a watertube boiler still removes 1,500 laborers). The design says recipe
  methods carry goods only and says nothing about the others.
- **A newer recipe mid-retool keeps what is done.** Levels already moved keep their recipe; every
  level not on the new target is to retool, oldest recipe first. Retool levels already queued
  continue and count toward the new target. Switching to a recipe that every level already runs
  costs nothing and ends retooling.
- **The newest recipe is taken directly.** Research that unlocks two recipes at once (or a country
  that already has both) moves straight to the newer one; the levels never pass through the middle.
- **Lags the design cannot express are left out and listed.** When the new recipe has none of a good
  the old one used (glassworks wood when moving to crystal glass, shipyard clippers when moving to
  metal shipbuilding), `old/new − 1` divides by zero and no `_mult` can restore it, so that good
  switches at once.
  `GENERATION_REPORT.json` lists every one.
- **Newest means last in the vanilla list.** Vanilla orders recipe groups oldest first; the generator
  does not check that every group is a strict progression.
- **Only research and new construction switch recipes.** Automation and any other multi-method group
  on a PMR building are hidden too and stay on whatever they run, in the building panel, the
  Buildings tab and the market panel's building lists.
- **Pollution has no lag.** It is a state modifier, not a building one.
- **Other `_mult`s on the same good combine with the lag additively**, exactly as the design notes
  for recipes: a +25% steel bonus during Blister → Bessemer gives 90 × (1 + 0.25 − 0.278 × (1 − p)).
- **The government share is read in 5% steps** through `country_ownership_fraction`, a ladder of
  constant comparisons. Its level count (`gov_levels`, used in the investor check) is exact up to 19
  levels and can be one off above that.
- **Investors need a group they score.** `bg_pmr_retool` is a child of `bg_manufacturing`, which
  Financial Districts score; standing alone, 1.14.5 never gave it a private investor. Countries
  whose private investment comes only from Manor Houses (which score manufacturing 0) may never
  retool their private share.
- **AI value steers the investment pool** (seen in game on 1.14.5): a 1,000,000 retool building is
  picked ahead of everything else, at home and abroad. That is why the ownership check matters.
- **The retool buildings are gated.** `potential` is true only while script holds a state variable
  for that retool, so neither shows in any construction list outside a retool.

## Assumptions about game script that are not verified in game

Everything below is read from the installed game's script and the generated docs in
`Documents\Paradox Interactive\Victoria 3\docs\`. None of it
has run yet; the run sheet says how each shows up when it fails.

1. `add_modifier` in building scope with per-good `goods_input_<g>_mult` / `goods_output_<g>_mult`
   moves that building's numbers. Documented for building scope; Ironroad's research found the engine
   reads building-scope goods modifiers, but never this exact pair.
2. `start_building_construction` and `start_privately_funded_building_construction` accept a modded
   building gated by a `potential` trigger, and calling one N × L times queues N × L levels.
3. `on_production_method_changed`, `on_building_built` and `on_building_expanded` fire with the building as root.
4. `level_after_queued_constructions` and `country_ownership_fraction` behave as documented.
5. `[THIS.GetBuilding.GetState...]` and `[THIS.Var('x').GetValue]` resolve inside `debug_log` text in
   building scope.
